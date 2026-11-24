"""Run the agent's tool calls against the database.

Inputs are validated here even though the API is given a schema: a bad input becomes an error
result the model can correct, never a bad row.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.tools import HANDOFF_TO_BROKER, MARK_OPTED_OUT, UPDATE_LEAD
from app.db import Database, Lead

log = logging.getLogger(__name__)


# Hand-off reason when the agent itself couldn't reply; not one the model can choose.
ASSISTANT_FAILED = "assistant_failed"


class UpdateLeadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    intent: Literal["buy", "rent"] | None = None
    budget: str | None = Field(default=None, min_length=1, max_length=100)
    area: str | None = Field(default=None, min_length=1, max_length=200)
    bhk: str | None = Field(default=None, min_length=1, max_length=50)
    timeline: str | None = Field(default=None, min_length=1, max_length=100)
    needs_loan: bool | None = None
    score: Literal["hot", "warm", "cold"] | None = None


class HandoffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    reason: Literal["hot_lead", "question", "complaint", "other"]


class OptOutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolOutcome:
    content: str
    is_error: bool = False


@dataclass
class Handoff:
    reason: str
    summary: str


class ToolHandlers:
    """Tool calls for one lead during one agent run. Keeps `lead` in step with what was saved."""

    def __init__(self, db: Database, lead: Lead) -> None:
        self._db = db
        self.lead = lead
        self.handoff: Handoff | None = None
        self.opted_out = False

    async def run(self, name: str, tool_input: Any) -> ToolOutcome:
        try:
            if name == UPDATE_LEAD:
                return await self._update_lead(UpdateLeadInput.model_validate(tool_input))
            if name == HANDOFF_TO_BROKER:
                return await self.hand_off(HandoffInput.model_validate(tool_input))
            if name == MARK_OPTED_OUT:
                OptOutInput.model_validate(tool_input or {})
                return await self.opt_out()
        except ValidationError as e:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}"
                for err in e.errors()
            )
            return ToolOutcome(f"Invalid input: {problems}", is_error=True)
        return ToolOutcome(f"Unknown tool: {name}", is_error=True)

    async def _update_lead(self, data: UpdateLeadInput) -> ToolOutcome:
        fields: dict[str, Any] = data.model_dump(exclude_none=True)
        if not fields:
            return ToolOutcome("Nothing to save: pass at least one field.", is_error=True)
        if self.lead.status == "new":
            fields["status"] = "qualifying"
        await self._db.update_lead(self.lead.id, fields)
        self.lead = self.lead.model_copy(update=fields)
        return ToolOutcome("Saved.")

    async def hand_off(self, data: HandoffInput) -> ToolOutcome:
        await self._mark_handed_off(Handoff(reason=data.reason, summary=data.summary))
        return ToolOutcome("Handed over. The broker will follow up with the lead.")

    async def hand_off_after_failure(self, summary: str) -> None:
        """The agent couldn't reply. A hand-off the model already made this turn is kept: its
        summary says what the lead wants."""
        if self.handoff is None:
            await self._mark_handed_off(Handoff(reason=ASSISTANT_FAILED, summary=summary))

    async def _mark_handed_off(self, handoff: Handoff) -> None:
        if self.lead.status != "handed_off":
            await self._db.update_lead(self.lead.id, {"status": "handed_off"})
            self.lead = self.lead.model_copy(update={"status": "handed_off"})
        self.handoff = handoff
        log.info("lead handed to broker", extra={"reason": handoff.reason})

    async def opt_out(self) -> ToolOutcome:
        await self._db.mark_opted_out(self.lead.id)
        self.lead = self.lead.model_copy(update={"opted_out": True, "status": "closed"})
        self.opted_out = True
        log.info("lead opted out")
        return ToolOutcome(
            "Opted out. Reply with one short line confirming they won't get more messages."
        )
