from __future__ import annotations

from pathlib import Path

import pytest

from als_intel.profile import profile_initials, public_profile_summary
from als_intel.store import EvidenceStore


def test_profile_initials_from_display_name() -> None:
    assert profile_initials(display_name="Jane Doe", email="jane@example.com") == "JD"


def test_profile_initials_from_email_when_name_missing() -> None:
    assert profile_initials(display_name="", email="santi.marquez@example.com") == "SM"


def test_public_profile_summary_includes_initials() -> None:
    summary = public_profile_summary(
        {
            "email": "reviewer@example.com",
            "display_name": "Review Lead",
            "title": "PI",
            "institution": "Lab",
            "has_avatar": False,
        }
    )
    assert summary["initials"] == "RL"
    assert summary["display_name"] == "Review Lead"


def test_store_user_profile_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "profile.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.get_or_create_user(user_id="usr_test", email="profile@example.com")

    updated = store.upsert_user_profile(
        user_id="usr_test",
        display_name="Profile User",
        title="Investigator",
        institution="Canoniga Lab",
        avatar_bytes=b"png-bytes",
        avatar_mime_type="image/png",
    )
    assert updated["display_name"] == "Profile User"
    assert updated["has_avatar"] is True

    loaded = store.get_user_profile(user_id="usr_test", include_avatar_bytes=True)
    assert loaded is not None
    assert loaded["avatar_data"] == b"png-bytes"
    assert loaded["avatar_mime_type"] == "image/png"

    cleared = store.upsert_user_profile(
        user_id="usr_test",
        display_name="Profile User",
        title="Investigator",
        institution="Canoniga Lab",
        clear_avatar=True,
    )
    assert cleared["has_avatar"] is False
