from sqlalchemy.orm import Session
from app.db import models


def get_document_by_id(db: Session, doc_id: int):
    """Fetches a single document by its primary key."""
    return db.query(models.Document).filter(models.Document.id == doc_id).first()

def get_all_documents(db: Session):
    """Fetches all processed documents, ordered by processing time."""
    return db.query(models.Document).order_by(models.Document.processed_at.desc()).all()

def create_document(db: Session, filename: str, method: str, status: str = "PROCESSING"):
    """
    Creates a new document record in the database.
    This should be called at the beginning of the processing pipeline.
    """
    db_document = models.Document(filename=filename, processing_method=method, status=status)
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

def update_document_status(db: Session, doc_id: int, status: str):
    """Updates the status of an existing document."""
    db_document = get_document_by_id(db, doc_id)
    if db_document:
        db_document.status = status
        db.commit()
        db.refresh(db_document)
    return db_document

def add_extracted_data(db: Session, doc_id: int, key: str, value: str, page: int, coords: str, method: str):
    """
    Adds a new extracted key-value pair to the database, associated with a document.
    """
    db_data = models.ExtractedData(
        document_id=doc_id,
        key=key,
        value=value,
        source_page=page,
        source_coordinates=coords,
        extraction_method=method
    )
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data

def clear_all_data(db: Session):
    """Deletes all records from all tables. Useful for a fresh start."""
    db.query(models.ExtractedData).delete()
    db.query(models.Document).delete()
    db.commit()
