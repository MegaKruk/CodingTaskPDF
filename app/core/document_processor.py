import os
import fitz
from sqlalchemy.orm import Session
from app.core.dynamic_extractor import DynamicExtractor
from app.db import crud


class DocumentProcessor:
    """
    Orchestrates the document processing pipeline using a dynamic approach.
    It does not rely on pre-defined templates.
    """

    def __init__(self, db_session: Session):
        """
        Initializes the processor.

        Args:
            db_session: An active SQLAlchemy session.
        """
        self.db = db_session
        self.extractor = DynamicExtractor()

    def process_document(self, pdf_path: str):
        """
        Main processing function for a single PDF file using dynamic extraction.

        Args:
            pdf_path: The full path to the PDF file.
        """
        filename = os.path.basename(pdf_path)
        print(f"Dynamically processing '{filename}'...")

        doc = None # Initialize doc to None to ensure it exists for the finally block
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Error opening PDF {filename}: {e}")
            crud.create_document(self.db, filename=filename, method="Dynamic", status="ERROR_OPENING_FILE")
            return

        db_document = crud.create_document(self.db, filename=filename, method="Dynamic Heuristic Engine",
                                           status="PROCESSING")

        try:
            extracted_elements = self.extractor.extract_all(doc)

            if not extracted_elements:
                print(f"No data automatically extracted from '{filename}'.")
                crud.update_document_status(self.db, db_document.id, "SUCCESS_NO_DATA")
                return

            for element in extracted_elements:
                key, value = element["key"], element["value"]
                page_num, coords_str, method = element["page_num"], element["coords"], element["method"]

                print(f"  - [{method}] Found '{key}': '{value}'")
                crud.add_extracted_data(self.db, db_document.id, key, value, page_num, coords_str, method)

            crud.update_document_status(self.db, db_document.id, "SUCCESS")
            print(f"Successfully processed '{filename}'.")

        except Exception as e:
            crud.update_document_status(self.db, db_document.id, "FAILED_EXTRACTION")
            print(f"Error during dynamic extraction for '{filename}': {e}")

        finally:
            # This block now safely closes the document. If an error
            # during processing has already invalidated or closed the document,
            # the `ValueError` is caught, preventing the application from crashing.
            if doc:
                try:
                    doc.close()
                except ValueError:
                    # Document is already closed, no action needed.
                    pass
