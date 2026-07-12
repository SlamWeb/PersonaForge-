from __future__ import annotations

import json

from personaforge.ingest.retrieve import ChildHit, ParentHit
from personaforge.persona.suggestions import validate_suggestions
from personaforge.web.service import (
    PersonaChatService,
    PreparedChat,
    WebConfig,
    list_local_personas,
    sources_from_parent_hits,
)
from personaforge.web.streaming import sse_event


def test_list_local_personas_finds_indexed_authors(tmp_path) -> None:
    index_dir = tmp_path / "authors" / "zhihu" / "alice" / "index"
    (index_dir / "qdrant").mkdir(parents=True)
    (index_dir / "parents.jsonl").write_text("", encoding="utf-8")

    personas = list_local_personas(tmp_path)

    assert [item.author for item in personas] == ["alice"]
    assert personas[0].source == "zhihu"
    assert personas[0].display_name == "alice"


def test_list_local_personas_reads_profile_metadata(tmp_path) -> None:
    author_dir = tmp_path / "authors" / "zhihu" / "alice"
    index_dir = author_dir / "index"
    (index_dir / "qdrant").mkdir(parents=True)
    (index_dir / "parents.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    (author_dir / "profile.json").write_text(
        json.dumps({"nickname": "Alice", "avatar_url": "https://example.com/a.jpg"}, ensure_ascii=False),
        encoding="utf-8",
    )

    persona = list_local_personas(tmp_path)[0]

    assert persona.display_name == "Alice"
    assert persona.avatar_url == "https://example.com/a.jpg"
    assert persona.content_count == 2


def test_save_turn_creates_author_scoped_session(tmp_path) -> None:
    service = PersonaChatService(WebConfig(data_dir=tmp_path))
    prepared = PreparedChat(
        session_id="s1",
        author="alice",
        query="问题？",
        query_mode="raw",
        writer_prompt="strong_identity",
        objective_background="",
        query_trace=None,
        retrieve_result=None,  # type: ignore[arg-type]
        messages=[],
    )

    service.save_turn(prepared, "回答", [{"rank": 1, "title": "来源"}])

    session = service.get_session("alice", "s1")
    assert session["title"] == "问题？"
    assert [message["role"] for message in session["messages"]] == ["user", "assistant"]
    assert service.list_sessions("alice")[0]["message_count"] == 2


def test_list_suggestions_reads_profile_suggestions(tmp_path) -> None:
    path = tmp_path / "authors" / "zhihu" / "alice" / "profile_suggestions.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"suggestions": ["一个新问题？"]}, ensure_ascii=False), encoding="utf-8")

    service = PersonaChatService(WebConfig(data_dir=tmp_path))

    assert service.list_suggestions("alice") == ["一个新问题？"]


def test_validate_suggestions_filters_near_duplicate_source_title() -> None:
    suggestions = validate_suggestions(
        [
            "为什么孩子越大越不愿意跟我们说话？",
            "为什么现在的年轻人越来越不想结婚？",
            "为什么很多父母越关心孩子，孩子越想逃？",
        ],
        source_titles=["为什么孩子越大越不愿意跟我们说话？", "为什么男人都不想结婚了？"],
        count=4,
    )

    assert suggestions == ["为什么很多父母越关心孩子，孩子越想逃？"]


def test_sources_from_parent_hits_hides_parent_full_text() -> None:
    hit = ParentHit(
        rank=1,
        parent_id="zhihu:answer:1",
        score=0.1,
        title="标题",
        path="answer/1.md",
        first_hits=[
            ChildHit(
                rank=3,
                score=0.2,
                node_id="node-1",
                parent_id="zhihu:answer:1",
                node_type="passage",
                title="标题",
                path="answer/1.md",
                route="literal_question:dense",
            )
        ],
        parent={"text": "完整正文不应该进 sources"},
    )

    sources = sources_from_parent_hits([hit])

    assert sources[0]["title"] == "标题"
    assert "完整正文" not in json.dumps(sources, ensure_ascii=False)
    assert sources[0]["first_hits"][0]["node_type"] == "passage"


def test_sse_event_serializes_utf8_json() -> None:
    event = sse_event("token", {"text": "你好"})

    assert event.startswith("event: token\n")
    assert 'data: {"text": "你好"}' in event
    assert event.endswith("\n\n")
