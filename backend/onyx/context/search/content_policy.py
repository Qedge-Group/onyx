"""Server-owned knowledge exclusions, independent of prompts and caller input."""

import re
from collections.abc import Iterable
from typing import TypeVar

# Scope by document-set name, never by a deployment-specific numeric Agent ID.
POLICIES: dict[str, tuple[str, ...]] = {
    "www.qedge.cn": (
        "科睿哲",
        "征收",
        "征拆",
        "拆迁",
        "棚改",
        "棚户区",
        "krz-news",
        "keruizhe",
        "land acquisition",
        "resettlement",
        "demolition",
    ),
}
T = TypeVar("T")


def excluded_terms(document_sets: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(term for name in document_sets for term in POLICIES.get(name, ()))
    )


def contains_excluded(text: str, document_sets: Iterable[str]) -> bool:
    text = re.sub(r"\s+", " ", text).casefold()
    return any(term.casefold() in text for term in excluded_terms(document_sets))


def filter_sections(sections: list[T], document_sets: Iterable[str]) -> list[T]:
    """Drop all retrieved sections of a document if any section violates scope."""
    names = tuple(document_sets)
    blocked = set()
    for section in sections:
        chunk = section.center_chunk  # type: ignore[attr-defined]
        text = "\n".join(
            (
                chunk.document_id,
                chunk.semantic_identifier or "",
                section.combined_content,
            )
        )  # type: ignore[attr-defined]
        if contains_excluded(text, names):
            blocked.add(chunk.document_id)
    return [
        section
        for section in sections
        if section.center_chunk.document_id not in blocked
    ]  # type: ignore[attr-defined]
