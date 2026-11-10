"""Central configuration, read from environment / .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "") -> str:
    """Like os.getenv, but treat blank values in .env as unset."""
    v = os.getenv(name)
    return v if v not in (None, "") else default


class Settings:
    # LLM: gemini | groq | openrouter | mock
    LLM_PROVIDER = _env("LLM_PROVIDER", "gemini").lower()
    LLM_MODEL = _env("LLM_MODEL", "")  # empty -> provider default
    GOOGLE_API_KEY = _env("GOOGLE_API_KEY", "")
    GROQ_API_KEY = _env("GROQ_API_KEY", "")
    OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY", "")

    # Postgres (Neon). Falls back to local SQLite when unset or blank.
    DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'app.db'}")

    # Pinecone (free Starter). Falls back to an in-memory store when unset or blank.
    PINECONE_API_KEY = _env("PINECONE_API_KEY", "")
    PINECONE_INDEX = _env("PINECONE_INDEX", "docgen-rag")
    PINECONE_CLOUD = _env("PINECONE_CLOUD", "aws")
    PINECONE_REGION = _env("PINECONE_REGION", "us-east-1")
    EMBEDDING_BACKEND = _env("EMBEDDING_BACKEND", "fastembed")  # fastembed | hash
    EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    EMBEDDING_DIM = 384

    WEB_SEARCH = _env("WEB_SEARCH", "true").lower() == "true"

    STORAGE_DIR = Path(_env("STORAGE_DIR", str(ROOT / "data" / "files")))
    MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "15"))
    MAX_UNZIPPED_MB = int(_env("MAX_UNZIPPED_MB", "120"))
    CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173").split(",")]
    API_KEY = _env("APP_API_KEY", "")  # optional shared secret for the API


settings = Settings()
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(ROOT / "data").mkdir(exist_ok=True)
