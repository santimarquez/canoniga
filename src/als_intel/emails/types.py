from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailContent:
    subject: str
    plain_text: str
    html: str
