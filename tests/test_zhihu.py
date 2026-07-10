from __future__ import annotations

import json

from personaforge.crawler.zhihu import (
    answer_payload_to_item,
    article_payload_to_item,
    blocked_reason_from_text,
    extract_items_from_initial_data,
    parse_user_token,
    pin_payload_to_item,
)


def test_parse_user_token_accepts_token_at_and_profile_url() -> None:
    assert parse_user_token("wu-ren-jun-28") == "wu-ren-jun-28"
    assert parse_user_token("@wu-ren-jun-28") == "wu-ren-jun-28"
    assert parse_user_token("https://www.zhihu.com/people/wu-ren-jun-28/answers") == "wu-ren-jun-28"


def test_answer_payload_to_item_maps_question_metadata() -> None:
    item = answer_payload_to_item(
        {
            "id": 42,
            "content": "<p>answer body</p>",
            "created_time": 1760000000,
            "updated_time": 1760000100,
            "voteup_count": 7,
            "comment_count": 3,
            "question": {"id": 9, "title": "question title"},
            "author": {"url_token": "alice"},
        },
        author_token=None,
        fetched_at="2026-01-01T00:00:00+00:00",
    )

    assert item.kind == "answer"
    assert item.id == "42"
    assert item.title == "question title"
    assert item.author_token == "alice"
    assert item.metadata["question_id"] == 9
    assert item.content_text == "answer body"


def test_article_payload_to_item_maps_url_and_counts() -> None:
    item = article_payload_to_item(
        {
            "id": "88",
            "title": "article title",
            "content": "<p>article body</p>",
            "voteup_count": 5,
            "comment_count": 1,
        },
        author_token="alice",
    )

    assert item.kind == "article"
    assert item.url == "https://zhuanlan.zhihu.com/p/88"
    assert item.metadata["voteup_count"] == 5


def test_pin_payload_to_item_handles_block_list_content() -> None:
    item = pin_payload_to_item(
        {
            "id": "77",
            "content": [
                {"type": "text", "content": "first line"},
                {"type": "image", "url": "https://example.com/a.png"},
            ],
            "like_count": 4,
        },
        author_token="alice",
    )

    assert item.kind == "pin"
    assert item.title.startswith("first line")
    assert "first line" in item.content_text
    assert item.metadata["like_count"] == 4


def test_blocked_reason_from_text_detects_common_failures() -> None:
    assert blocked_reason_from_text("forbidden") == "forbidden"
    assert blocked_reason_from_text("captcha required") == "captcha"
    assert blocked_reason_from_text("AuthenticationInvalidClient") == "authentication invalid"


def test_extract_items_from_initial_data_matches_zhihu_page_entities() -> None:
    initial_data = {
        "initialState": {
            "entities": {
                "answers": {
                    "42": {
                        "id": 42,
                        "content": "<p>answer body</p>",
                        "question": {"id": 9, "title": "question title"},
                        "author": {"url_token": "alice"},
                    }
                },
                "articles": {
                    "88": {
                        "id": 88,
                        "title": "article title",
                        "content": "<p>article body</p>",
                        "author": {"url_token": "alice"},
                    }
                },
                "pins": {
                    "77": {
                        "id": 77,
                        "content": [{"type": "text", "content": "pin body"}],
                        "author": {"url_token": "alice"},
                    }
                },
            }
        }
    }
    html = (
        "<html><body>"
        f"<script id=\"js-initialData\" type=\"application/json\">{json.dumps(initial_data)}</script>"
        "</body></html>"
    )

    items = extract_items_from_initial_data(html, author_token="fallback")

    by_kind = {item.kind: item for item in items}
    assert by_kind["answer"].metadata["question_id"] == 9
    assert by_kind["answer"].title == "question title"
    assert by_kind["article"].title == "article title"
    assert by_kind["pin"].content_text == "pin body"
