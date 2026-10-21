"""App settings, read from environment variables (and an optional .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'kasiledger.db'}")

# AI provider switches
EXTRACTOR = _env("EXTRACTOR", "rule_based").lower()
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen2.5:3b")
SPEECH = _env("SPEECH", "none").lower()
WHISPER_MODEL = _env("WHISPER_MODEL", "base")
OCR = _env("OCR", "tesseract").lower()
TESSERACT_CMD = _env("TESSERACT_CMD")  # e.g. C:\\Program Files\\Tesseract-OCR\\tesseract.exe on Windows

# Channels
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_MODE = _env("TELEGRAM_MODE", "polling").lower()
WHATSAPP_TOKEN = _env("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = _env("WHATSAPP_VERIFY_TOKEN", "kasiledger-verify")
WHATSAPP_API_VERSION = _env("WHATSAPP_API_VERSION", "v21.0")

PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
DAILY_SUMMARY_TIME = _env("DAILY_SUMMARY_TIME")
