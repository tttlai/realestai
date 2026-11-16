"""Tools the agent can call. Inputs are checked again in handlers.py before anything is saved.

Site-visit booking (get_visit_slots / book_visit) arrives with the calendar in phase 5. Until
then the agent asks for a preferred time and hands the lead to the broker.
"""

from typing import Any

UPDATE_LEAD = "update_lead"
HANDOFF_TO_BROKER = "handoff_to_broker"
MARK_OPTED_OUT = "mark_opted_out"

TOOLS: list[dict[str, Any]] = [
    {
        "name": UPDATE_LEAD,
        "description": (
            "Save details learned from the conversation. Call it as soon as you learn any of "
            "these, passing only the fields you learned or that changed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The lead's name"},
                "intent": {"type": "string", "enum": ["buy", "rent"]},
                "budget": {
                    "type": "string",
                    "description": "In the lead's words, e.g. '80-90 lakh' or '25k per month'",
                },
                "area": {"type": "string", "description": "Preferred area(s), e.g. 'Wakad'"},
                "bhk": {"type": "string", "description": "e.g. '2 BHK'"},
                "timeline": {
                    "type": "string",
                    "description": "When they want to buy or move, e.g. 'within 3 months'",
                },
                "needs_loan": {"type": "boolean", "description": "Whether they need a home loan"},
                "score": {"type": "string", "enum": ["hot", "warm", "cold"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": HANDOFF_TO_BROKER,
        "description": (
            "Pass the lead to the broker: when they are hot or want a site visit, ask something "
            "the listed properties don't answer, are upset, or want to talk to a person."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "One or two lines for the broker: name, requirement, budget, area, "
                        "timeline, and what the lead wants next (e.g. preferred visit time)"
                    ),
                },
                "reason": {
                    "type": "string",
                    "enum": ["hot_lead", "question", "complaint", "other"],
                },
            },
            "required": ["summary", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": MARK_OPTED_OUT,
        "description": "The lead asked not to be contacted again, in any language.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
