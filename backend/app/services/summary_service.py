from __future__ import annotations

from datetime import datetime, timezone

SUMMARY_METHOD = "mock"
SUMMARY_MAX_LENGTH = 160


def generate_mock_summary(text: str) -> dict[str, object]:
    if not text.strip():
        raise ValueError("Material has no text available for summary")

    compact_text = " ".join(text.split())
    return {
        "ai_summary": f"Mock summary: {compact_text[:SUMMARY_MAX_LENGTH]}",
        "summary_generated": True,
        "summary_method": SUMMARY_METHOD,
        "summary_updated_at": datetime.now(timezone.utc),
    }
