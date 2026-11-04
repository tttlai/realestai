from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import get_settings
from app.db import Database
from app.log import configure_logging
from app.webhooks import whatsapp as whatsapp_webhook
from app.whatsapp.client import WhatsAppClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as http:
        app.state.db = await Database.connect(settings)
        app.state.whatsapp = WhatsAppClient(http, settings.meta_graph_version)
        yield


app = FastAPI(title="Realest AI WhatsApp Lead Bot", lifespan=lifespan)
app.include_router(whatsapp_webhook.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
