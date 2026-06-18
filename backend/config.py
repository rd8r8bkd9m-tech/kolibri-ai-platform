import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("KOLIBRI_DATA_DIR", "/opt/kolibri-ai/data"))
FRONTEND_DIR = Path(os.getenv("KOLIBRI_FRONTEND_DIR", "/opt/kolibri-ai/frontend/dist"))
MIMO_BIN = os.getenv("KOLIBRI_MIMO_BIN", "/root/.mimocode/bin/mimo")

DB_PATH = DATA_DIR / "kolibri.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

JWT_SECRET = os.getenv("KOLIBRI_JWT_SECRET", "CHANGE-ME-IN-PRODUCTION")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("KOLIBRI_JWT_ACCESS_EXPIRE_MINUTES", "60"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("KOLIBRI_JWT_REFRESH_EXPIRE_DAYS", "30"))

CORS_ORIGINS = os.getenv("KOLIBRI_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

RATE_LIMIT_REQUESTS = int(os.getenv("KOLIBRI_RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("KOLIBRI_RATE_LIMIT_WINDOW", "60"))

RAG_SERVICE_URL = os.getenv("KOLIBRI_RAG_URL", "http://10.99.0.3:8002")
AGENT_SERVICE_URL = os.getenv("KOLIBRI_AGENT_URL", "http://10.99.0.4:8003")
INFERENCE_SERVICE_URL = os.getenv("KOLIBRI_INFERENCE_URL", "http://10.99.0.5:8001")
CLUSTER_SERVICE_URL = os.getenv("KOLIBRI_CLUSTER_URL", "http://127.0.0.1:9001")
TTS_OUTPUT_DIR = Path(os.getenv("KOLIBRI_TTS_DIR", str(DATA_DIR / "tts")))
TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AI_API_KEY = os.getenv("KOLIBRI_AI_API_KEY", "")
AI_BASE_URL = os.getenv("KOLIBRI_AI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.getenv("KOLIBRI_AI_MODEL", "mimo-v2.5-pro")
