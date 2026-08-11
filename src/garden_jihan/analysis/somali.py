from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SomaliAnnotation:
    verbatim: str
    normalized: str | None
    dialect_group: str
    subvariety: str | None = None
    region: str | None = None
    code_switching: tuple[str, ...] = ()


def preserve_dialect(annotation: SomaliAnnotation) -> dict[str, str | None]:
    """Return both dialect-faithful and normalized text without silently replacing either."""
    return {
        "display": annotation.verbatim,
        "normalized": annotation.normalized,
        "dialect_group": annotation.dialect_group,
    }
