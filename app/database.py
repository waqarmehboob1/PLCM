import os
from sqlmodel import create_engine, Session, SQLModel
from dotenv import load_dotenv
from app.models.tables import *  # Ensure all models are imported so they are registered with SQLModel
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=False)

def init_db() -> None:
    """Create tables."""
    SQLModel.metadata.create_all(engine)

def close_db() -> None:
    """Dispose engine (cleanup)."""
    engine.dispose()

def get_session():
    with Session(engine) as session:
        yield session