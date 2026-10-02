from __future__ import annotations

import re
from datetime import datetime, timezone

CARD_COUNT = 3
CARD_METHOD = "mock"
CARD_QUESTIONS = (
    "What is the core topic of this material?",
    "Which key idea should you review from this material?",
    "How would you explain this material in one sentence?",
)


def generate_mock_cards(material_id: int, text: str) -> dict[str, object]:
    if not text.strip():
        raise ValueError("Material has no text available for card generation")

    fragments = [fragment.strip() for fragment in re.split(r"(?<=[.!?])\s+", text) if fragment.strip()] or [text]
    created_at = datetime.now(timezone.utc)
    cards = []
    for index in range(CARD_COUNT):
        cards.append(
            {
                "id": material_id * 100 + index + 1,
                "question": CARD_QUESTIONS[index],
                "answer": fragments[index % len(fragments)][:240],
                "source_material_id": material_id,
                "card_type": "concept" if index == 0 else "review",
                "created_at": created_at.isoformat(),
            }
        )

    return {
        "cards": cards,
        "cards_generated": True,
        "cards_generated_at": created_at,
        "cards_method": CARD_METHOD,
    }
