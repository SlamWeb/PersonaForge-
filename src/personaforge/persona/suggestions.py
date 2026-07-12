"""Generate product-facing suggested questions for a local persona."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from personaforge.llm import JsonChatClient


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    suggestions: list[str]
    source_title_count: int
    path: Path


def generate_suggestions(
    *,
    author: str,
    index_dir: Path,
    out_path: Path,
    llm: JsonChatClient,
    count: int = 6,
    source_limit: int = 80,
) -> SuggestionResult:
    titles = collect_source_titles(index_dir, limit=source_limit)
    if not titles:
        raise ValueError(f"No source titles found in {index_dir / 'parents.jsonl'}")
    candidate_count = max(count * 2, count + 4)
    payload = llm.complete_json(
        build_suggestion_messages(titles=titles, count=candidate_count),
        temperature=0.65,
        max_tokens=900,
    )
    raw_items = payload.get("suggestions")
    if not isinstance(raw_items, list):
        raise ValueError(f"Expected suggestions list from LLM, got: {payload!r}")
    suggestions = validate_suggestions(raw_items, source_titles=titles, count=count)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "author": author,
                "source": "generated_from_history_titles",
                "suggestions": suggestions,
                "source_title_count": len(titles),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return SuggestionResult(suggestions=suggestions, source_title_count=len(titles), path=out_path)


def collect_source_titles(index_dir: Path, *, limit: int = 80) -> list[str]:
    path = index_dir / "parents.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            title = clean_question(str(row.get("title") or ""))
            if row.get("kind") == "answer" and is_good_source_title(title):
                rows.append(row | {"title": title})
    rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    titles: list[str] = []
    seen: set[str] = set()
    for row in rows:
        title = str(row["title"])
        if title in seen:
            continue
        seen.add(title)
        titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def build_suggestion_messages(*, titles: list[str], count: int) -> list[dict[str, str]]:
    numbered = "\n".join(f"{idx + 1}. {title}" for idx, title in enumerate(titles))
    return [
        {
            "role": "system",
            "content": (
                "你是一个中文产品里的建议问题生成器。"
                "你只负责根据某位创作者的历史问题标题，生成适合用户继续提问的新问题。"
                "不要回答问题，不要模仿作者，不要输出解释。必须输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请生成 {count} 个新的知乎式问题，用于放在聊天产品首页作为建议问题。\n\n"
                "要求：\n"
                "1. 只能借用历史标题体现出的主题领域，不要复用原问题。\n"
                "2. 不要生成和任何历史标题语义过近的问题，避免用户点击后直接召回原回答。\n"
                "3. 问题要像真实用户会问的知乎问题，口语、自然、具体。\n"
                "4. 每个问题 12 到 38 个中文字符左右。\n"
                "5. 不要包含具体历史事件、人名、链接、编号。\n"
                "6. 只输出 JSON：{\"suggestions\":[\"问题1？\",\"问题2？\"]}\n\n"
                "历史问题标题：\n"
                f"{numbered}"
            ),
        },
    ]


def validate_suggestions(raw_items: list[object], *, source_titles: list[str], count: int) -> list[str]:
    suggestions: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = clean_question(str(item))
        if not is_good_suggestion(text):
            continue
        if text in seen:
            continue
        if any(too_similar(text, title) for title in source_titles):
            continue
        seen.add(text)
        suggestions.append(text)
        if len(suggestions) >= count:
            break
    return suggestions


def clean_question(text: str) -> str:
    return " ".join(text.strip().strip('"“”').split())


def is_good_source_title(text: str) -> bool:
    return 6 <= len(text) <= 90 and "http" not in text.lower()


def is_good_suggestion(text: str) -> bool:
    if not (8 <= len(text) <= 60):
        return False
    if "http" in text.lower() or "\n" in text:
        return False
    return text.endswith(("?", "？"))


def too_similar(left: str, right: str) -> bool:
    if left == right:
        return True
    if has_shared_phrase(left, right, min_length=5):
        return True
    left_chars = meaningful_chars(left)
    right_chars = meaningful_chars(right)
    if not left_chars or not right_chars:
        return False
    overlap = len(left_chars & right_chars) / max(1, min(len(left_chars), len(right_chars)))
    return overlap >= 0.68


def has_shared_phrase(left: str, right: str, *, min_length: int) -> bool:
    left_clean = normalize_for_phrase(left)
    right_clean = normalize_for_phrase(right)
    if len(left_clean) < min_length or len(right_clean) < min_length:
        return False
    phrases = {
        left_clean[index : index + min_length]
        for index in range(0, len(left_clean) - min_length + 1)
    }
    return any(phrase in right_clean for phrase in phrases)


def normalize_for_phrase(text: str) -> str:
    ignored = set(" \t\r\n，。！？!?、；;：《》“”\"'（）()[]【】")
    return "".join(char for char in text if char not in ignored)


def meaningful_chars(text: str) -> set[str]:
    ignored = set(" 的了吗呢啊吧是和与在对如何为什么怎么看看待一个一些很多有没有是否可以应该")
    return {char for char in text if char.strip() and char not in ignored}
