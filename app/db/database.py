import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# Define the path for the SQLite database.
# It will be created in the project root directory.
DATABASE_URL = "sqlite:///app.db"

# Create the SQLAlchemy engine.
# connect_args is needed for SQLite to handle multi-threaded access,
# which is common in web apps like Streamlit.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a session factory. This will be used to create new DB sessions.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our ORM models. All models will inherit from this.
Base = declarative_base()

def init_db():
    """
    Initializes the database by creating all tables defined in the models.
    This function should be called once at the start of the application.
    """
    # Import all models here before calling create_all
    # to ensure they are registered with the Base metadata.
    from app.db.models import Document, ExtractedData
    Base.metadata.create_all(bind=engine)
