import os
from sqlalchemy import create_engine, MetaData
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# Note: check_same_thread=False is needed for SQLite in FastAPI/multithreaded envs
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
metadata_obj = MetaData()

def get_engine():
    return engine
