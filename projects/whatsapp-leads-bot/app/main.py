import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import anthropic
import httpx
from fastapi import FastAPI

from app.agent.run import Agent
from app.config import Settings, get_settings
from app.db import Database
from app.log import configure_logging
from app.webhooks import whatsapp as whatsapp_webhook
from app.whatsapp.client import WhatsAppClient

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    async with AsyncExitStack() as stack:
        http = await stack.enter_async_context(httpx.AsyncClient(timeout=httpx.Timeout(10.0)))
        app.state.db = await Database.connect(settings)
        app.state.whatsapp = WhatsAppClient(http, settings.meta_graph_version)
        app.state.agent = await _make_agent(settings, app.state.db, stack)
        yield


async def _make_agent(settings: Settings, db: Database, stack: AsyncExitStack) -> Agent | None:
    if settings.anthropic_api_key is None:
        log.warning("ANTHROPIC_API_KEY is not set: messages are stored but not replied to")
        return None
    llm = await stack.enter_async_context(
        anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=60.0, max_retries=2
        )
    )
    return Agent(llm, db, default_model=settings.default_model, effort=settings.agent_effort)


app = FastAPI(title="Realest AI WhatsApp Lead Bot", lifespan=lifespan)
app.include_router(whatsapp_webhook.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
