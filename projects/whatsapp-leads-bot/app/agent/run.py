"""The agent loop: call Claude with tools, run the tool calls, repeat until it writes a reply.

Every run is saved to agent_logs (model, tokens, each tool call and its result, the reply), so
any message the bot sent can be explained to the broker.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import anthropic
from anthropic.types import Message, MessageParam

from app.agent.handlers import Handoff, ToolHandlers
from app.agent.prices import unlisted_amounts
from app.agent.prompt import build_system, utc_now
from app.agent.tools import MARK_OPTED_OUT, TOOLS
from app.db import Broker, Database, Lead, StoredMessage

log = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_TOKENS = 16_000
HISTORY_LIMIT = 20

# Replies that opt out without asking the model. Anything subtler ("not interested", "mat
# bhejo") is left to the model, which handles any language.
STOP_KEYWORDS = {"stop", "stop all", "unsubscribe", "opt out", "optout"}
STOP_CONFIRMATION = "Done, you won't get any more messages from us. Thank you!"
FALLBACK_REPLY = "Thanks for your message! {broker} will get back to you shortly."
FALLBACK_SUMMARY = "The assistant couldn't reply automatically. Please read the chat and reply."


@dataclass
class AgentReply:
    text: str | None
    lead: Lead
    opted_out: bool = False
    handoff: Handoff | None = None


@dataclass
class _Run:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def add_usage(self, response: Message) -> None:
        u = response.usage
        self.input_tokens += (
            u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
        )
        self.output_tokens += u.output_tokens


class Agent:
    def __init__(
        self,
        llm: anthropic.AsyncAnthropic,
        db: Database,
        *,
        default_model: str,
        effort: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._llm = llm
        self._db = db
        self._default_model = default_model
        self._effort = effort
        self._clock = clock

    async def reply(self, broker: Broker, lead: Lead) -> AgentReply:
        """Work out the reply to the lead's latest message. Never raises for an API failure:
        the lead gets a holding reply and is handed to the broker instead."""
        history = await self._db.recent_messages(lead.id, HISTORY_LIMIT)
        handlers = ToolHandlers(self._db, lead)

        latest = next((m for m in reversed(history) if m.direction == "inbound"), None)
        if latest is not None and is_stop_keyword(latest.body):
            return await self._keyword_opt_out(handlers)

        messages = to_api_messages(history)
        if not messages:
            log.warning("no inbound message to reply to")
            return AgentReply(text=None, lead=lead)

        properties = await self._db.list_available_properties(broker.id)
        system = build_system(broker, properties, lead, self._clock())
        run = _Run(model=broker.model or self._default_model)

        text: str | None = None
        failure = "max_iterations"
        try:
            for _ in range(MAX_ITERATIONS):
                response = await self._llm.messages.create(
                    model=run.model,
                    max_tokens=MAX_TOKENS,
                    system=system,  # type: ignore[arg-type]
                    tools=TOOLS,  # type: ignore[arg-type]
                    messages=messages,
                    output_config={"effort": self._effort},  # type: ignore[typeddict-item]
                )
                run.add_usage(response)
                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append(
                        {"role": "user", "content": await self._run_tools(response, handlers, run)}
                    )
                    continue
                # max_tokens or refusal: a cut-off or missing reply is worse than the fallback.
                text = _text(response) if response.stop_reason == "end_turn" else None
                failure = str(response.stop_reason)
                break
        except anthropic.APIError as e:
            failure = f"api_error:{type(e).__name__}"
            log.exception("claude api call failed")

        if text:
            lead_texts = [m.body for m in history if m.direction == "inbound" and m.body]
            if made_up := unlisted_amounts(text, properties, lead_texts):
                log.warning("reply mentions a price that is not listed", extra={"amounts": made_up})
        else:
            log.warning("agent produced no reply", extra={"reason": failure})
            run.tool_calls.append({"name": "fallback", "input": {"reason": failure}})
            if handlers.opted_out:
                # They opted out before the failure: confirm that, and promise no contact.
                text = STOP_CONFIRMATION
            else:
                await handlers.hand_off_after_failure(FALLBACK_SUMMARY)
                text = FALLBACK_REPLY.format(broker=broker.name)

        await self._db.insert_agent_log(
            lead_id=lead.id,
            model=run.model,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            tool_calls=run.tool_calls,
            reply=text,
        )
        log.info(
            "agent replied",
            extra={
                "model": run.model,
                "tools": [c["name"] for c in run.tool_calls],
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
            },
        )
        return AgentReply(
            text=text, lead=handlers.lead, opted_out=handlers.opted_out, handoff=handlers.handoff
        )

    async def _run_tools(
        self, response: Message, handlers: ToolHandlers, run: _Run
    ) -> list[dict[str, Any]]:
        """Run every tool call in the response; all results go back in one user message."""
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            outcome = await handlers.run(block.name, block.input)
            run.tool_calls.append(
                {
                    "name": block.name,
                    "input": block.input,
                    "result": outcome.content,
                    "is_error": outcome.is_error,
                }
            )
            result: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": outcome.content,
            }
            if outcome.is_error:
                result["is_error"] = True
            results.append(result)
        return results

    async def _keyword_opt_out(self, handlers: ToolHandlers) -> AgentReply:
        outcome = await handlers.opt_out()
        await self._db.insert_agent_log(
            lead_id=handlers.lead.id,
            model="none (stop keyword)",
            input_tokens=0,
            output_tokens=0,
            tool_calls=[{"name": MARK_OPTED_OUT, "input": {}, "result": outcome.content}],
            reply=STOP_CONFIRMATION,
        )
        return AgentReply(text=STOP_CONFIRMATION, lead=handlers.lead, opted_out=True)


def to_api_messages(history: list[StoredMessage]) -> list[MessageParam]:
    """Stored messages as API turns: inbound -> user, outbound -> assistant.

    The list must start with the lead, and consecutive messages from the same side are joined.
    """
    messages: list[MessageParam] = []
    for m in history:
        role = "user" if m.direction == "inbound" else "assistant"
        if not messages and role == "assistant":
            continue
        body = m.body or f"[{m.kind} message]"
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] = f"{messages[-1]['content']}\n\n{body}"
        else:
            messages.append({"role": role, "content": body})
    return messages


def is_stop_keyword(text: str | None) -> bool:
    if not text:
        return False
    return re.sub(r"[^\w\s]", "", text).strip().lower() in STOP_KEYWORDS


def _text(response: Message) -> str | None:
    text = "\n\n".join(b.text for b in response.content if b.type == "text").strip()
    return text or None
