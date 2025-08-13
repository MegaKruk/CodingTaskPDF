from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class Document(Base):
    """
    Represents a processed PDF document in the database.
    Stores metadata about the document and its processing status.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    # This field now describes the extraction method used.
    processing_method = Column(String, nullable=True)
    status = Column(String, default="PENDING")  # e.g., PENDING, SUCCESS, FAILED
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Establish a one-to-many relationship with ExtractedData
    extracted_data = relationship("ExtractedData", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class ExtractedData(Base):
    """
    Represents a single key-value pair extracted from a document.
    Linked to a parent Document.
    """
    __tablename__ = "extracted_data"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False)
    value = Column(String, nullable=True)
    # Storing coordinates allows for UI highlighting
    source_coordinates = Column(String, nullable=True)  # Stored as "x0,y0,x1,y1"
    source_page = Column(Integer, nullable=True)
    extraction_method = Column(String, nullable=True)  # e.g., Heuristic, Table, Widget

    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)

    # Establish a many-to-one relationship with Document
    document = relationship("Document", back_populates="extracted_data")

    def __repr__(self):
        return f"<ExtractedData(id={self.id}, key='{self.key}', value='{self.value}')>"
