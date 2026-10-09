from __future__ import annotations

PROMPT_VERSION = "knowledge_canonicalization_v1"
CONFIGURATION_VERSION = "canonicalization_config_v1"

SYSTEM_PROMPT = """You judge whether course knowledge candidates express the same learnable concept.
Return one JSON object with this shape:
{"groups":[{"candidate_ids":[1,2],"same_concept":true,"canonical_name":"...","canonical_description":"...","reason":"..."}]}

Rules:
- Merge only concept identity, never merely related, prerequisite, parent-child, same-chapter, or similar topics.
- False merge is worse than false split. If uncertain, omit the group and keep candidates separate.
- Candidate IDs must come only from the supplied block. Each candidate ID may appear in at most one group.
- Output only groups containing at least two different candidate IDs.
- For a true group, canonical_name must be a concise standard term already expressed by the candidates.
- canonical_description must be a faithful 1-3 sentence semantic intersection of the supplied descriptions.
- Do not invent a broader theory, hierarchy, prerequisite, relation, or new fact.
- Cache, Cache Hit, Cache Miss, Cache Replacement, and LRU Replacement are related but distinct.
- L1 Cache and L2 Cache are distinct.
- LRU Replacement and Least Recently Used Replacement may be identical.
- Source snippets are evidence context only. Never rewrite or return source excerpts.
- If no candidates are certainly identical, return {"groups":[]}.
"""


def messages(candidate_context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Judge same-concept identity only for this bounded candidate block. "
                f"Candidate data:\n{candidate_context}"
            ),
        },
    ]
