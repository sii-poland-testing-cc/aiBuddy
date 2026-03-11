"""
AI Buddy – FastAPI backend
Exposes LlamaIndex Workflows as streaming SSE endpoints.
"""

import sys
from pathlib import Path

# When run as `python app/main.py`, Python puts backend/app/ on sys.path instead
# of backend/, so `import app` fails. This ensures backend/ is always present.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, projects, files, context, snapshots
from app.core.config import settings
from app.db.engine import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_buddy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("🚀 AI Buddy backend starting…")
    yield
    logger.info("🛑 AI Buddy backend shutting down…")


app = FastAPI(
    title="AI Buddy API",
    version="0.1.0",
    description="QA Agent powered by LlamaIndex Workflows + Amazon Bedrock",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(context.router,   prefix="/api/context",   tags=["M1 – Context Builder"])
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["Audit Snapshots"])
app.include_router(chat.router,      prefix="/api/chat",      tags=["Chat"])
app.include_router(projects.router,  prefix="/api/projects",  tags=["Projects"])
app.include_router(files.router,     prefix="/api/files",     tags=["Files"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
