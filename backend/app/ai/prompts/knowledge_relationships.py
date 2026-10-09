from __future__ import annotations

PROMPT_VERSION = "knowledge_relationships_v1"

SYSTEM_PROMPT = """You model only defensible directed relationships among supplied canonical course knowledge nodes.
Return one JSON object with this shape:
{"contains_edges":[{"source_node_id":1,"target_node_id":2,"reason":"...","evidence":[{"material_id":1,"source_reference":"segment-1"}]}],"prerequisite_edges":[...]}

Relationship semantics:
- CONTAINS: source_node_id is the broader parent concept; target_node_id is its direct child concept.
- PREREQUISITE: source_node_id is knowledge a learner needs first; target_node_id is the dependent concept.

Rules:
- Use only node IDs supplied in this bounded block. Never invent an ID, node, material, or source reference.
- Be sparse. Omit uncertain relationships, siblings, merely related concepts, and indirect relationships.
- Do not create PREREQUISITE solely because a CONTAINS relationship exists.
- Do not create self edges, duplicate directed relationships, cyclic containment, or multiple containment parents.
- Do not create prerequisite cycles.
- A course may have multiple CONTAINS roots; that is normal.
- Every edge needs a concise reason. Add material evidence only when the supplied node evidence directly supports it.
- For material evidence, copy material_id and source_reference exactly from supplied node evidence.
- If no direct citation exists, return an empty evidence list; never fabricate citations.
- Source excerpts are context only. Do not return excerpts or introduce facts absent from the input.
- If there are no defensible relationships, return both arrays empty.
"""


def messages(node_context: str, feedback: str | None = None) -> list[dict[str, str]]:
    instruction = "Infer relationships only within this bounded canonical-node block."
    if feedback:
        instruction = f"{instruction} Correct the previous invalid output: {feedback}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{instruction}\nCanonical nodes:\n{node_context}"},
    ]
