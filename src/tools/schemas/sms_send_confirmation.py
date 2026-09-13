"""Tool Schema: sms_send_confirmation.

Authoritative specification: DOCS/AGENT_LOGIC_SPEC.md Section 4.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SMSSendInput(BaseModel):
    """Input payload for dispatching driver SMS confirmation."""

    model_config = ConfigDict(extra="ignore")

    recipient_phone_e164: str = Field(..., description="Target driver phone in E.164 format")
    message_body: str = Field(..., description="SMS message text with navigation/dock details")
    locale: str = Field(default="en-US", description="Language locale")


class SMSSendOutput(BaseModel):
    """Result of driver SMS dispatch."""

    model_config = ConfigDict(extra="ignore")

    sms_sent: bool = Field(..., description="Whether carrier SMS gateway accepted the dispatch")
    provider_message_id: Optional[str] = Field(default=None, description="SMS gateway tracking ID")
    error: Optional[str] = Field(default=None, description="Error message if SMS delivery failed")
