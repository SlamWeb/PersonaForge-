from __future__ import annotations

import json

from personaforge.crawler.markdown import html_to_markdown, item_filename, write_markdown_corpus, write_profile
from personaforge.crawler.models import ContentItem, CreatorProfile


def make_item() -> ContentItem:
    return ContentItem(
        source="zhihu",
        kind="answer",
        id="123",
        title="Why test crawler?",
        url="https://www.zhihu.com/question/1/answer/123",
        author_token="alice",
        content_html=(
            "<p>Hello<br><strong>world</strong></p>"
            '<p><a href="https://example.com">link</a></p>'
            '<p><img src="https://example.com/a.png" alt="pic"></p>'
        ),
        content_text="Hello\nworld",
        fetched_at="2026-01-01T00:00:00+00:00",
        metadata={"question_id": "1", "comment_count": 2},
    )


def test_html_to_markdown_handles_common_rich_text() -> None:
    markdown = html_to_markdown(make_item().content_html)

    assert "Hello\n**world**" in markdown
    assert "[link](https://example.com)" in markdown
    assert "![pic](https://example.com/a.png)" in markdown


def test_write_markdown_corpus_and_manifest(tmp_path) -> None:
    item = make_item()

    paths = write_markdown_corpus([item], tmp_path)

    assert len(paths) == 1
    assert paths[0].parent == tmp_path / "answer"
    text = paths[0].read_text(encoding="utf-8")
    assert 'source: "zhihu"' in text
    assert 'kind: "answer"' in text
    assert "# Why test crawler?" in text

    manifest_lines = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == 1
    manifest = json.loads(manifest_lines[0])
    assert manifest["id"] == "123"
    assert manifest["path"] == "answer/answer-123-Why-test-crawler.md"


def test_write_profile(tmp_path) -> None:
    profile = CreatorProfile(
        source="zhihu",
        author_token="alice",
        nickname="Alice",
        profile_url="https://www.zhihu.com/people/alice",
        avatar_url="https://example.com/avatar.jpg",
    )

    path = write_profile(profile, tmp_path)

    assert path.name == "profile.json"
    assert json.loads(path.read_text(encoding="utf-8"))["nickname"] == "Alice"


def test_item_filename_removes_windows_invalid_chars() -> None:
    item = make_item()
    item.title = 'bad/name:*?"<>| title'

    filename = item_filename(item)

    assert filename.endswith(".md")
    assert "/" not in filename
    assert ":" not in filename
    assert "?" not in filename
