"""Build title, lead, and passage texts from parent documents."""

from __future__ import annotations

import re

IMAGE_ONLY_RE = re.compile(r"\s*(?:!\[[^\]]*\]\([^)]+\)\s*)+\Z")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


def split_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for part in re.split(r"\n\s*\n+", text):
        paragraph = part.strip()
        if not paragraph or is_pure_image_paragraph(paragraph):
            continue
        paragraphs.append(paragraph)
    return paragraphs


def is_pure_image_paragraph(text: str) -> bool:
    return bool(IMAGE_ONLY_RE.fullmatch(text.strip()))


def build_lead(text: str, *, target_chars: int = 800) -> str:
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return ""

    selected: list[str] = []
    total = 0
    for paragraph in paragraphs:
        selected.append(paragraph)
        total += len(paragraph)
        if total >= target_chars:
            break
    return "\n\n".join(selected).strip()


def build_passages(
    text: str,
    *,
    target_chars: int = 900,
    max_chars: int = 1400,
    min_chars: int = 250,
) -> list[str]:
    units = _split_long_paragraphs(split_paragraphs(text), max_chars=max_chars)
    if not units:
        return []

    passages: list[str] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        unit_len = len(unit)
        would_exceed_max = current and current_len + unit_len > max_chars
        if would_exceed_max and current_len >= min_chars:
            passages.append("\n\n".join(current).strip())
            current = [unit]
            current_len = unit_len
            continue

        current.append(unit)
        current_len += unit_len
        if current_len >= target_chars:
            passages.append("\n\n".join(current).strip())
            current = []
            current_len = 0

    if current:
        tail = "\n\n".join(current).strip()
        if passages and len(tail) < min_chars:
            passages[-1] = f"{passages[-1]}\n\n{tail}".strip()
        else:
            passages.append(tail)

    return [passage for passage in passages if passage]


def normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _split_long_paragraphs(paragraphs: list[str], *, max_chars: int) -> list[str]:
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue

        current: list[str] = []
        current_len = 0
        for sentence in _sentences(paragraph):
            if current and current_len + len(sentence) > max_chars:
                units.append("".join(current).strip())
                current = [sentence]
                current_len = len(sentence)
            else:
                current.append(sentence)
                current_len += len(sentence)
        if current:
            units.append("".join(current).strip())
    return [unit for unit in units if unit]


def _sentences(paragraph: str) -> list[str]:
    pieces = [piece.strip() for piece in SENTENCE_SPLIT_RE.split(paragraph) if piece.strip()]
    if not pieces:
        return [paragraph]
    return pieces

