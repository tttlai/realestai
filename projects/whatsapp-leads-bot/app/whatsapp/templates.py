"""Approved WhatsApp templates: names, languages and how their parameters are filled.

Each broker's WhatsApp Business Account needs its own copy of every template, approved by Meta,
with exactly the name, language and body below. README.md has the steps.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    name: str
    language: str
    body: str  # as submitted to Meta, with {{1}}, {{2}}... placeholders

    def render(self, params: list[str]) -> str:
        """The text the lead sees, stored in `messages` so the agent knows what was sent."""
        return re.sub(r"\{\{(\d+)\}\}", lambda m: params[int(m.group(1)) - 1], self.body)


# First message to a lead from a form or portal email, who hasn't messaged the broker yet.
# {{1}} lead's name, {{2}} what they enquired about, {{3}} the agency.
LEAD_OPENER = Template(
    name="lead_opener",
    language="en",
    body=(
        "Hi {{1}}, thanks for your enquiry about {{2}} with {{3}}. Are you looking to buy or rent?"
    ),
)


def template_param(value: str | None, fallback: str, max_length: int = 60) -> str:
    """A safe parameter value: Meta rejects empty values, newlines, tabs and long runs of spaces."""
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text or fallback


def lead_opener_params(name: str | None, enquiry: str | None, agency: str) -> list[str]:
    first_name = (name or "").strip().split(" ")[0] if name else None
    return [
        template_param(first_name, "there", 40),
        template_param(enquiry, "your property search"),
        template_param(agency, agency or "us"),
    ]


# To the broker's alert number when a lead is hot.
# {{1}} lead's name, {{2}} lead's number, {{3}} one-line summary.
HOT_LEAD_ALERT = Template(
    name="hot_lead_alert",
    language="en",
    body="New hot lead for you: {{1}}, {{2}}. {{3}} Please call or WhatsApp them soon.",
)

# To the broker's alert number when a lead needs a person for any other reason (a question the
# listings don't answer, a complaint, asked for a person, or the assistant failed).
LEAD_NEEDS_REPLY = Template(
    name="lead_needs_reply",
    language="en",
    body="A lead needs a reply from you: {{1}}, {{2}}. {{3}} Please call or WhatsApp them soon.",
)


def broker_alert_params(name: str | None, phone: str, summary: str) -> list[str]:
    sentence = template_param(summary, "No details were noted.", 600)
    if sentence[-1] not in ".!?…।":
        sentence += "."
    return [template_param(name, "Name not given"), f"+{phone}", sentence]
