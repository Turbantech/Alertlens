"""Memo schema. Literal types mean the model can never output e.g. 'CLOSED'."""
from typing import Literal
from pydantic import BaseModel

class RedFlag(BaseModel):
    description: str
    evidence: list[str]          # transaction ids or profile fields
    policy_citation: str         # e.g. "structuring.md §2.2"

class MemoModel(BaseModel):
    alert_id: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    red_flags: list[RedFlag]
    sanctions_result: str
    recommendation: Literal["ESCALATE", "RECOMMEND_CLOSE"]
    summary: str