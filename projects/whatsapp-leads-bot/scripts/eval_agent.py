"""Run the sample conversations through the real agent and check the results.

    uv run python -m scripts.eval_agent                   # all conversations
    uv run python -m scripts.eval_agent --only hindi_kharadi --model claude-sonnet-5-5

Needs ANTHROPIC_API_KEY (from the environment or .env) and calls the Claude API, so each run
costs a little. Nothing touches Supabase or WhatsApp: each conversation runs against an
in-memory database loaded with scripts/sample_properties.json.

Conversations are in tests/fixtures/conversations.json. For each one it prints the chat, the
saved lead details and the tool calls, then checks:
- no reply mentions a rupee amount that isn't a listed price (or something the lead said)
- the conversation's expectations: intent, area, BHK, loan, score, hand-off reason, opt-out

Read the replies too: tone, language and one question at a time can't be checked by code.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
from dotenv import dotenv_values

from app.agent.prices import unlisted_amounts
from app.agent.run import Agent
from app.config import Settings
from app.db import Lead
from scripts.seed_properties import SAMPLE_FILE, load_rows
from tests.fakes import FakeDatabase

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "conversations.json"
EXPECT_KEYS = {
    "intent",
    "area_contains",
    "bhk_contains",
    "name_contains",
    "needs_loan",
    "score",
    "handoff_reason",
    "opted_out",
    "no_tools",
    "reply_has_devanagari",
}


def load_conversations(path: Path = FIXTURES) -> list[dict[str, Any]]:
    conversations: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    for c in conversations:
        unknown = set(c.get("expect", {})) - EXPECT_KEYS
        if unknown:
            raise ValueError(f"{c['name']}: unknown expectations {sorted(unknown)}")
    return conversations


async def run_conversation(
    llm: anthropic.AsyncAnthropic, model: str, effort: str, conversation: dict[str, Any]
) -> list[str]:
    """Play the lead's turns, print the chat, and return the failed checks."""
    db = FakeDatabase()  # a fresh in-memory database per conversation
    agent = Agent(llm, db, default_model=model, effort=effort)  # type: ignore[arg-type]
    broker = db.add_broker(
        name="Ravi",
        agency_name="Ravi Realty",
        access_token_enc="unused",  # noqa: S106  # nothing is sent to WhatsApp
    )
    await db.replace_properties(broker.id, load_rows(SAMPLE_FILE))
    properties = await db.list_available_properties(broker.id)
    lead = await db.get_or_create_lead(broker.id, "919876543210", name=None, source="whatsapp")

    failures: list[str] = []
    replies: list[str] = []
    lead_texts: list[str] = []
    handoff_reasons: list[str] = []
    print(f"\n=== {conversation['name']}: {conversation.get('about', '')}")
    for turn in conversation["turns"]:
        print(f"  lead : {turn}")
        lead_texts.append(turn)
        await db.insert_message(
            lead_id=lead.id, direction="inbound", kind="text", body=turn, wa_message_id=None
        )
        result = await agent.reply(broker, db.lead(lead.id))
        reply = result.text or ""
        replies.append(reply)
        print(f"  bot  : {reply}")
        if result.handoff:
            handoff_reasons.append(result.handoff.reason)
        await db.insert_message(
            lead_id=lead.id, direction="outbound", kind="text", body=reply, wa_message_id=None
        )
        if made_up := unlisted_amounts(reply, properties, lead_texts):
            failures.append(f"reply mentions unlisted amounts {made_up}: {reply!r}")

    final = db.lead(lead.id)
    tools = [c["name"] for log_row in db.agent_logs for c in log_row["tool_calls"]]
    print(f"  saved: {_lead_summary(final)}")
    print(f"  tools: {', '.join(tools) or 'none'}")
    failures += check_expectations(
        conversation.get("expect", {}), final, tools, handoff_reasons, replies
    )
    return failures


def check_expectations(
    expect: dict[str, Any],
    lead: Lead,
    tools: list[str],
    handoff_reasons: list[str],
    replies: list[str],
) -> list[str]:
    failures = []

    def check(ok: bool, what: str) -> None:
        if not ok:
            failures.append(what)

    if "intent" in expect:
        check(lead.intent == expect["intent"], f"intent {lead.intent!r} != {expect['intent']!r}")
    for field in ("area", "bhk", "name"):
        key = f"{field}_contains"
        if key in expect:
            value = getattr(lead, field) or ""
            check(expect[key].lower() in value.lower(), f"{field} {value!r} lacks {expect[key]!r}")
    if "needs_loan" in expect:
        check(lead.needs_loan == expect["needs_loan"], f"needs_loan is {lead.needs_loan}")
    if "score" in expect:
        check(lead.score == expect["score"], f"score {lead.score!r} != {expect['score']!r}")
    if "handoff_reason" in expect:
        check(
            expect["handoff_reason"] in handoff_reasons,
            f"no hand-off with reason {expect['handoff_reason']!r} (got {handoff_reasons})",
        )
    if "opted_out" in expect:
        check(lead.opted_out == expect["opted_out"], f"opted_out is {lead.opted_out}")
    if expect.get("no_tools"):
        check(not tools, f"expected no tool calls, got {tools}")
    if expect.get("reply_has_devanagari"):
        check(all(re.search(r"[ऀ-ॿ]", r) for r in replies), "a reply is not in Hindi")
    return failures


def _lead_summary(lead: Lead) -> str:
    fields = ["name", "intent", "budget", "area", "bhk", "timeline", "needs_loan", "score"]
    known = {f: getattr(lead, f) for f in fields if getattr(lead, f) is not None}
    return (
        ", ".join(f"{k}={v}" for k, v in known.items())
        + f" | status={lead.status}"
        + (" | OPTED OUT" if lead.opted_out else "")
    )


def api_key() -> str | None:
    """From the environment or .env, without needing the rest of the app's settings."""
    return os.environ.get("ANTHROPIC_API_KEY") or dotenv_values(".env").get("ANTHROPIC_API_KEY")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", help="run just this conversation (repeatable)")
    parser.add_argument("--model", default=Settings.model_fields["default_model"].default)
    parser.add_argument("--effort", default=Settings.model_fields["agent_effort"].default)
    args = parser.parse_args(argv)

    key = api_key()
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set (environment or .env)")
    conversations = load_conversations()
    if args.only:
        conversations = [c for c in conversations if c["name"] in args.only]
        if not conversations:
            raise SystemExit(f"no conversation named {args.only}")

    print(f"model={args.model} effort={args.effort}")
    results: dict[str, list[str]] = {}
    async with anthropic.AsyncAnthropic(api_key=key) as llm:
        for conversation in conversations:
            results[conversation["name"]] = await run_conversation(
                llm, args.model, args.effort, conversation
            )

    print("\n=== Summary")
    for name, failures in results.items():
        print(f"  {'PASS' if not failures else 'FAIL'}  {name}")
        for failure in failures:
            print(f"        - {failure}")
    return 1 if any(results.values()) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Hindi and ₹ on Windows consoles
    sys.exit(asyncio.run(main()))
