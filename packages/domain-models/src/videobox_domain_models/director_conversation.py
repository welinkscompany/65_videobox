from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectorMessage:
    message_id: str
    conversation_id: str
    project_id: str
    session_id: str
    role: str
    text: str
    proposal_id: str | None
    client_message_id: str | None
    created_at: str
