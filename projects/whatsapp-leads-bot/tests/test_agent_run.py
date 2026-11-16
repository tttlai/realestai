import logging
from datetime import UTC, datetime

import anthropic
import httpx2
import pytest

from app.agent.run import (
    FALLBACK_REPLY,
    MAX_ITERATIONS,
    Agent,
    AgentReply,
    is_stop_keyword,
    to_api_messages,
)
from app.db import Broker, Lead, StoredMessage
from tests.fakes import FakeDatabase, FakeLLM, text_response, tool_response

NOW = datetime(2026, 11, 16, 10, 30, tzinfo=UTC)


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def broker(db: FakeDatabase) -> Broker:
    broker = db.add_broker(access_token_enc="unused")
    db.add_property(
        broker.id,
        title="Skyline Residency",
        area="Wakad",
        bhk="2 BHK",
        type="sale",
        price_min=8_500_000,
        price_max=9_500_000,
    )
    db.add_property(broker.id, title="Old Listing", area="Wakad", status="sold")
    return broker


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def agent(llm: FakeLLM, db: FakeDatabase) -> Agent:
    return Agent(llm, db, default_model="claude-haiku-5-5", effort="medium", clock=lambda: NOW)  # type: ignore[arg-type]


async def say(db: FakeDatabase, broker: Broker, *texts: str) -> Lead:
    lead = await db.get_or_create_lead(broker.id, "919876543210", name="Asha", source="whatsapp")
    for text in texts:
        await db.insert_message(
            lead_id=lead.id, direction="inbound", kind="text", body=text, wa_message_id=None
        )
    return lead


async def test_request_carries_prompt_tools_history_and_effort(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    lead = await say(db, broker, "2bhk wakad mein kitna hai?")
    llm.queue(text_response("Skyline Residency mein 2 BHK ₹85 L - ₹95 L hai. Buy ya rent?"))

    reply = await agent.reply(broker, lead)

    assert reply.text == "Skyline Residency mein 2 BHK ₹85 L - ₹95 L hai. Buy ya rent?"
    [call] = llm.calls
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_config"] == {"effort": "medium"}
    assert {t["name"] for t in call["tools"]} == {
        "update_lead",
        "handoff_to_broker",
        "mark_opted_out",
    }
    assert call["messages"] == [{"role": "user", "content": "2bhk wakad mein kitna hai?"}]
    stable, volatile = call["system"]
    assert stable["cache_control"] == {"type": "ephemeral"}
    assert "Skyline Residency | Wakad | 2 BHK | for sale | ₹85 L - ₹95 L" in stable["text"]
    assert "Old Listing" not in stable["text"]
    assert "Asha" in volatile["text"] and "Asha" not in stable["text"]
    assert "Monday 16 November 2026, 16:00 (Asia/Kolkata)" in volatile["text"]


async def test_broker_model_overrides_default(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    broker = broker.model_copy(update={"model": "claude-sonnet-5-5"})
    await agent.reply(broker, await say(db, broker, "hi"))
    assert llm.calls[0]["model"] == "claude-sonnet-5-5"
    assert db.agent_logs[0]["model"] == "claude-sonnet-5-5"


async def test_tool_calls_save_lead_details_then_reply(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    lead = await say(db, broker, "buy karna hai, wakad, 90 lakh tak")
    details = {"intent": "buy", "area": "Wakad", "budget": "up to 90 lakh", "score": "warm"}
    llm.queue(tool_response(("update_lead", details)), text_response("Kitne BHK chahiye?"))

    reply = await agent.reply(broker, lead)

    assert reply.text == "Kitne BHK chahiye?"
    saved = db.lead(lead.id)
    assert (saved.intent, saved.area, saved.budget, saved.score) == (
        "buy",
        "Wakad",
        "up to 90 lakh",
        "warm",
    )
    assert saved.status == "qualifying"
    assert reply.lead.area == "Wakad"

    # The second request replays the assistant turn unchanged (thinking included) and answers
    # each tool call by id, in one user message.
    second = llm.calls[1]
    assistant, results = second["messages"][-2:]
    assert [b.type for b in assistant["content"]] == ["thinking", "tool_use"]
    tool_use = assistant["content"][1]
    assert results == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": "Saved."}],
    }

    [log_row] = db.agent_logs
    assert log_row["tool_calls"] == [
        {"name": "update_lead", "input": details, "result": "Saved.", "is_error": False}
    ]
    assert (log_row["input_tokens"], log_row["output_tokens"]) == (300, 40)
    assert log_row["reply"] == "Kitne BHK chahiye?"


async def test_invalid_tool_input_is_returned_as_an_error_and_not_saved(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    lead = await say(db, broker, "hi")
    llm.queue(
        tool_response(("update_lead", {"intent": "lease", "colour": "blue"}), ("teleport", {})),
        text_response("Buy or rent?"),
    )

    await agent.reply(broker, lead)

    results = llm.calls[1]["messages"][-1]["content"]
    assert [r["is_error"] for r in results] == [True, True]
    assert "intent" in results[0]["content"] and "colour" in results[0]["content"]
    assert results[1]["content"] == "Unknown tool: teleport"
    assert db.lead(lead.id).intent is None


async def test_handoff_marks_lead_and_is_reported(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    lead = await say(db, broker, "Saturday 11am visit chahiye")
    summary = "Asha, 2 BHK Wakad, 90 L, wants a visit Saturday 11am"
    llm.queue(
        tool_response(("handoff_to_broker", {"summary": summary, "reason": "hot_lead"})),
        text_response("Test Broker will confirm your Saturday visit shortly."),
    )

    reply = await agent.reply(broker, lead)

    assert reply.handoff is not None and reply.handoff.reason == "hot_lead"
    assert reply.handoff.summary == summary
    assert db.lead(lead.id).status == "handed_off"


async def test_model_opt_out_is_saved_and_confirmed(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    lead = await say(db, broker, "mujhe aur message mat bhejo")
    db.followups.append({"lead_id": lead.id, "sent": False, "cancelled": False})
    llm.queue(
        tool_response(("mark_opted_out", {})), text_response("Theek hai, ab message nahi aayega.")
    )

    reply = await agent.reply(broker, lead)

    assert reply.opted_out and reply.text == "Theek hai, ab message nahi aayega."
    assert db.lead(lead.id).opted_out
    assert db.followups[0]["cancelled"] is True


@pytest.mark.parametrize("text", ["STOP", "stop.", " Unsubscribe ", "Stop all"])
async def test_stop_keyword_skips_the_model(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker, text: str
) -> None:
    reply = await agent.reply(broker, await say(db, broker, text))
    assert reply.opted_out
    assert llm.calls == []
    assert db.agent_logs[0]["model"] == "none (stop keyword)"


async def fallback_case(
    agent: Agent, db: FakeDatabase, broker: Broker
) -> tuple[AgentReply, list[dict[str, object]]]:
    lead = await say(db, broker, "hi")
    reply = await agent.reply(broker, lead)
    assert reply.text == FALLBACK_REPLY.format(broker="Test Broker")
    assert db.lead(lead.id).status == "handed_off"
    [log_row] = db.agent_logs
    return reply, log_row["tool_calls"]  # type: ignore[return-value]


async def test_too_many_tool_rounds_falls_back_to_a_holding_reply(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    llm.queue(*[tool_response(("update_lead", {"name": "Asha"}))] * MAX_ITERATIONS)
    _, calls = await fallback_case(agent, db, broker)
    assert len(llm.calls) == MAX_ITERATIONS
    assert calls[-1] == {"name": "fallback", "input": {"reason": "max_iterations"}}


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_refusal_or_cut_off_reply_falls_back(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker, stop_reason: str
) -> None:
    llm.queue(text_response("partial", stop_reason=stop_reason))
    _, calls = await fallback_case(agent, db, broker)
    assert calls[-1] == {"name": "fallback", "input": {"reason": stop_reason}}


async def test_api_failure_falls_back(
    agent: Agent, llm: FakeLLM, db: FakeDatabase, broker: Broker
) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    llm.queue(anthropic.APIConnectionError(request=request))
    _, calls = await fallback_case(agent, db, broker)
    assert calls[-1] == {"name": "fallback", "input": {"reason": "api_error:APIConnectionError"}}


async def test_unlisted_price_is_logged(
    agent: Agent,
    llm: FakeLLM,
    db: FakeDatabase,
    broker: Broker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    lead = await say(db, broker, "budget 70 lakh hai")
    llm.queue(text_response("70 lakh mein Wakad mein ₹75 L ka flat mil sakta hai"))
    with caplog.at_level(logging.WARNING):
        await agent.reply(broker, lead)
    [record] = [r for r in caplog.records if "price" in r.getMessage()]
    assert record.amounts == [7_500_000]  # type: ignore[attr-defined]


def test_history_becomes_alternating_turns_starting_with_the_lead() -> None:
    history = [
        StoredMessage(direction="outbound", kind="template", body="Thanks for enquiring!"),
        StoredMessage(direction="inbound", body="hi"),
        StoredMessage(direction="inbound", kind="image", body=None),
        StoredMessage(direction="outbound", body="Buy or rent?"),
        StoredMessage(direction="inbound", body="buy"),
    ]
    assert to_api_messages(history) == [
        {"role": "user", "content": "hi\n\n[image message]"},
        {"role": "assistant", "content": "Buy or rent?"},
        {"role": "user", "content": "buy"},
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("STOP", True),
        ("stop!", True),
        ("opt out", True),
        ("stop calling at night", False),
        (None, False),
    ],
)
def test_stop_keywords(text: str | None, expected: bool) -> None:
    assert is_stop_keyword(text) is expected
