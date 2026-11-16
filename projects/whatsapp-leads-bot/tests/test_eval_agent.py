"""The evaluation script, run against the fake model (the real one costs money)."""

from scripts import eval_agent
from tests.fakes import FakeLLM, text_response, tool_response


def test_fixtures_load_with_known_expectations() -> None:
    conversations = eval_agent.load_conversations()
    names = [c["name"] for c in conversations]
    assert len(names) == len(set(names)) >= 10
    assert "hinglish_2bhk_wakad" in names


def by_name(name: str) -> dict[str, object]:
    return next(c for c in eval_agent.load_conversations() if c["name"] == name)


async def test_stop_keyword_conversation_passes_without_the_model() -> None:
    llm = FakeLLM()
    failures = await eval_agent.run_conversation(
        llm,  # type: ignore[arg-type]
        "claude-haiku-5-5",
        "medium",
        by_name("stop_keyword"),
    )
    assert failures == []
    assert llm.calls == []


async def test_failed_expectations_and_made_up_prices_are_reported() -> None:
    llm = FakeLLM()
    llm.queue(
        tool_response(("update_lead", {"intent": "rent"})),
        text_response("Bungalows there start at 4 crore."),
    )
    conversation = {
        "name": "t",
        "turns": ["4 BHK bungalow in Koregaon Park?"],
        "expect": {"intent": "buy", "no_tools": True},
    }
    failures = await eval_agent.run_conversation(llm, "m", "low", conversation)  # type: ignore[arg-type]
    assert any("unlisted amounts [40000000]" in f for f in failures)
    assert any("intent 'rent' != 'buy'" in f for f in failures)
    assert any("expected no tool calls" in f for f in failures)
