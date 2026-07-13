from __future__ import annotations


def profile_initials(*, display_name: str, email: str) -> str:
    name = str(display_name or "").strip()
    if name:
        parts = [part for part in name.replace(".", " ").split() if part]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            token = parts[0]
            return (token[:2] if len(token) >= 2 else token[:1]).upper()
    local = str(email or "").split("@", 1)[0].strip()
    if not local:
        return "U"
    chunks = [chunk for chunk in local.replace(".", " ").replace("_", " ").split() if chunk]
    if len(chunks) >= 2:
        return (chunks[0][0] + chunks[1][0]).upper()
    return (local[:2] if len(local) >= 2 else local[:1]).upper()


def public_profile_summary(profile: dict[str, object]) -> dict[str, object]:
    return {
        "display_name": str(profile.get("display_name") or ""),
        "title": str(profile.get("title") or ""),
        "institution": str(profile.get("institution") or ""),
        "has_avatar": bool(profile.get("has_avatar")),
        "initials": profile_initials(
            display_name=str(profile.get("display_name") or ""),
            email=str(profile.get("email") or ""),
        ),
    }
