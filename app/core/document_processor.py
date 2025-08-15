import os
import fitz
from sqlalchemy.orm import Session
from app.core.config_manager import ConfigManager
from app.core.extractor import Extractor
from app.core.dynamic_extractor import DynamicExtractor
from app.db import crud


class DocumentProcessor:
    """Orchestrates document processing using config-based or dynamic extraction."""

    def __init__(self, db_session: Session, config_manager: ConfigManager):
        self.db = db_session
        self.config_manager = config_manager
        self.config_extractor = Extractor()
        self.dynamic_extractor = DynamicExtractor()

    def process_document(self, pdf_path: str, mode: str):
        """Process a PDF document using the specified mode."""
        filename = os.path.basename(pdf_path)
        print(f"Processing '{filename}' using {mode} mode...")

        # Open the PDF
        doc = None
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Error opening PDF {filename}: {e}")
            crud.create_document(
                self.db,
                filename=filename,
                method=mode,
                status="ERROR_OPENING_FILE"
            )
            return

        # Process based on mode
        if mode == "Precise (Config-Based)":
            self._process_with_config(doc, filename)
        else:
            self._process_dynamically(doc, filename)

        if doc:
            doc.close()

    def _process_with_config(self, doc: fitz.Document, filename: str):
        """Process document using configuration-based extraction."""
        # Identify form type
        form_type = self.config_manager.identify_form_type(doc)
        if not form_type:
            print(f"No matching config found for '{filename}'. Falling back to dynamic mode.")
            # Fallback to dynamic extraction
            self._process_dynamically(doc, filename, fallback=True)
            return

        config = self.config_manager.configs.get(form_type)
        if not config:
            print(f"Error retrieving config for form type '{form_type}'.")
            crud.create_document(
                self.db,
                filename=filename,
                method="Config-Based",
                status="CONFIG_ERROR"
            )
            return

        # Create document record
        db_document = crud.create_document(
            self.db,
            filename=filename,
            method=f"Config: {form_type}",
            status="PROCESSING"
        )

        # Extract fields and checkboxes
        fields_config = config.get("data_elements", {}).get("fields", [])
        checkboxes_config = config.get("data_elements", {}).get("checkboxes", [])

        # Process each page
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Extract fields for this page
            page_fields = [f for f in fields_config if f.get("page_num", 0) == page_num]
            if page_fields:
                extracted_fields = self.config_extractor.find_all_fields_on_page(page, page_fields)

                for field in extracted_fields:
                    if field['value']:  # Only save non-empty values
                        print(f"  - [Field] {field['name']}: '{field['value']}'")
                        coords_str = f"{field['rect'].x0:.1f},{field['rect'].y0:.1f},{field['rect'].x1:.1f},{field['rect'].y1:.1f}"
                        crud.add_extracted_data(
                            db=self.db,
                            doc_id=db_document.id,
                            key=field['name'],
                            value=field['value'],
                            page=page_num,
                            coords=coords_str,
                            method="Config Field"
                        )

            # Extract checkboxes for this page
            page_checkboxes = [c for c in checkboxes_config if c.get("page_num", 0) == page_num]
            for checkbox in page_checkboxes:
                key = checkbox["name"]
                value, rect = self.config_extractor.find_checkbox_near_label(
                    page,
                    checkbox.get("label", key),
                    instance=checkbox.get("instance", 0)
                )

                if value != "Not Found":
                    print(f"  - [Checkbox] {key}: '{value}'")
                    coords_str = f"{rect.x0:.1f},{rect.y0:.1f},{rect.x1:.1f},{rect.y1:.1f}" if rect else "0,0,0,0"
                    crud.add_extracted_data(
                        db=self.db,
                        doc_id=db_document.id,
                        key=key,
                        value=value,
                        page=page_num,
                        coords=coords_str,
                        method="Config Checkbox"
                    )

        crud.update_document_status(self.db, db_document.id, "SUCCESS")

    def _process_dynamically(self, doc: fitz.Document, filename: str, fallback: bool = False):
        """Process document using dynamic heuristic extraction."""
        method = "Dynamic (Fallback)" if fallback else "Dynamic Heuristic"

        # Create document record
        db_document = crud.create_document(
            self.db,
            filename=filename,
            method=method,
            status="PROCESSING"
        )

        # Extract using dynamic extractor
        extracted_elements = self.dynamic_extractor.extract_all(doc)

        if not extracted_elements:
            crud.update_document_status(self.db, db_document.id, "SUCCESS_NO_DATA")
            print(f"  No data extracted from '{filename}'")
            return

        # Save extracted data
        for element in extracted_elements:
            print(f"  - [{element['method']}] {element['key']}: '{element['value']}'")
            crud.add_extracted_data(
                db=self.db,
                doc_id=db_document.id,
                key=element["key"],
                value=element["value"],
                page=element["page_num"],
                coords=element["coords"],
                method=element["method"]
            )

        crud.update_document_status(self.db, db_document.id, "SUCCESS")
        print(f"  Extracted {len(extracted_elements)} data elements from '{filename}'")