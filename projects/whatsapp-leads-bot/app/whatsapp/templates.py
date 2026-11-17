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
