import os
import fitz
from sqlalchemy.orm import Session
from app.core.config_manager import ConfigManager
from app.core.extractor import Extractor
from app.core.dynamic_extractor import DynamicExtractor
from app.db import crud


class DocumentProcessor:
    """Orchestrates document processing using either a config or dynamic approach."""

    def __init__(self, db_session: Session, config_manager: ConfigManager):
        self.db = db_session
        self.config_manager = config_manager
        self.config_extractor = Extractor()
        self.dynamic_extractor = DynamicExtractor()

    def process_document(self, pdf_path: str, mode: str):
        filename = os.path.basename(pdf_path)
        print(f"Processing '{filename}' using {mode} mode...")
        doc = None
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Error opening PDF {filename}: {e}")
            crud.create_document(self.db, filename=filename, method=mode, status="ERROR_OPENING_FILE")
            return

        if mode == "Precise (Config-Based)":
            self._process_with_config(doc, filename)
        else:
            self._process_dynamically(doc, filename)

        if doc: doc.close()

    def _process_with_config(self, doc: fitz.Document, filename: str):
        form_type = self.config_manager.identify_form_type(doc)
        if not form_type:
            print(f"No matching config found for '{filename}'. Skipping.")
            crud.create_document(self.db, filename=filename, method="Config-Based", status="NO_CONFIG_FOUND")
            return

        config = self.config_manager.configs.get(form_type)
        if not config:
            print(f"Error retrieving config for form type '{form_type}'.")
            crud.create_document(self.db, filename=filename, method="Config-Based", status="CONFIG_ERROR")
            return

        db_document = crud.create_document(self.db, filename=filename, method=f"Config: {form_type}",
                                           status="PROCESSING")

        fields = config.get("data_elements", {}).get("fields", [])
        checkboxes = config.get("data_elements", {}).get("checkboxes", [])
        all_elements = fields + checkboxes

        # This context list is crucial for the boundary-aware logic
        all_field_labels = [f['label'] for f in fields]

        for element in all_elements:
            key = element["name"]
            page_num = element.get("page_num", 0)
            page = doc[page_num]

            # Add the context list to the parameters for the extractor
            element['all_labels'] = all_field_labels

            if any(f['name'] == key for f in fields):
                method_name, extraction_method = "find_text_right_of_label", "Config Field"
            else:
                method_name, extraction_method = "find_checkbox_near_label", "Config Checkbox"

            method = getattr(self.config_extractor, method_name)
            value, rect = method(page, **element)

            print(f"  - [{extraction_method}] Found '{key}': '{value}'")

            coords_str = f"{rect.x0},{rect.y0},{rect.x1},{rect.y1}" if rect else None

            crud.add_extracted_data(
                db=self.db, doc_id=db_document.id, key=key, value=value,
                page=page_num, coords=coords_str, method=extraction_method
            )

        crud.update_document_status(self.db, db_document.id, "SUCCESS")

    def _process_dynamically(self, doc: fitz.Document, filename: str):
        db_document = crud.create_document(self.db, filename=filename, method="Dynamic Heuristic", status="PROCESSING")

        extracted_elements = self.dynamic_extractor.extract_all(doc)
        if not extracted_elements:
            crud.update_document_status(self.db, db_document.id, "SUCCESS_NO_DATA")
            return

        for element in extracted_elements:
            print(f"  - [{element['method']}] Found '{element['key']}': '{element['value']}'")
            crud.add_extracted_data(
                db=self.db, doc_id=db_document.id, key=element["key"], value=element["value"],
                page=element["page_num"], coords=element["coords"], method=element["method"]
            )
        crud.update_document_status(self.db, db_document.id, "SUCCESS")
