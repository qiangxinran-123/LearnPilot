from __future__ import annotations


def normalize_source_reference(reference: str | None) -> str | None:
    if reference is None:
        return None
    normalized = reference.strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1].strip()
    return normalized


def resolve_source_reference(reference: str | None, allowed_references: set[str]) -> str | None:
    """Resolve presentation-only bracket/spacing variants without inventing references."""

    normalized = normalize_source_reference(reference)
    if normalized is None or normalized in allowed_references:
        return normalized

    compact = normalized.replace(" ", "")
    matches = [candidate for candidate in allowed_references if candidate.replace(" ", "") == compact]
    return matches[0] if len(matches) == 1 else normalized
