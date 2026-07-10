from __future__ import annotations

import json

from personaforge import cli
from personaforge.ingest.build import build_corpus
from personaforge.ingest.chunking import build_lead, build_passages
from personaforge.ingest.loader import load_parent_documents
from personaforge.ingest.nodes import build_nodes_for_parent


def write_raw_item(raw_dir, *, kind: str = "answer", source_id: str = "1", body: str | None = None) -> None:
    item_dir = raw_dir / kind
    item_dir.mkdir(parents=True, exist_ok=True)
    path = item_dir / f"{kind}-{source_id}-Title-{source_id}.md"
    content = body or "第一段。\n\n第二段。"
    path.write_text(
        (
            "---\n"
            'source: "zhihu"\n'
            f'kind: "{kind}"\n'
            f'id: "{source_id}"\n'
            f'title: "Title {source_id}"\n'
            'url: "https://example.local/item"\n'
            'author_token: "alice"\n'
            "comment_count: 2\n"
            "---\n\n"
            f"# Title {source_id}\n\n"
            f"{content}\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "source": "zhihu",
        "kind": kind,
        "id": source_id,
        "title": f"Title {source_id}",
        "path": f"{kind}/{path.name}",
    }
    manifest_path = raw_dir / "manifest.jsonl"
    with manifest_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False) + "\n")


def test_load_parent_documents_uses_manifest_path(tmp_path) -> None:
    write_raw_item(tmp_path, kind="answer", source_id="123")

    parents = load_parent_documents(tmp_path)

    assert len(parents) == 1
    parent = parents[0]
    assert parent.doc_id == "zhihu:answer:123"
    assert parent.path == "answer/answer-123-Title-123.md"
    assert parent.metadata["comment_count"] == 2
    assert parent.text == "第一段。\n\n第二段。"


def test_load_parent_documents_supports_legacy_flat_manifest(tmp_path) -> None:
    path = tmp_path / "pin-9-短想法.md"
    path.write_text(
        (
            "---\n"
            'source: "zhihu"\n'
            'kind: "pin"\n'
            'id: "9"\n'
            'title: "短想法"\n'
            "---\n\n"
            "# 短想法\n\n"
            "一点想法。\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps({"kind": "pin", "id": "9"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    parents = load_parent_documents(tmp_path)

    assert len(parents) == 1
    assert parents[0].doc_id == "zhihu:pin:9"
    assert parents[0].path == "pin-9-短想法.md"


def test_chunking_builds_lead_and_passages() -> None:
    text = "\n\n".join([f"第{i}段。" * 80 for i in range(1, 6)])

    lead = build_lead(text, target_chars=300)
    passages = build_passages(text, target_chars=500, max_chars=700, min_chars=100)

    assert lead.startswith("第1段。")
    assert len(passages) >= 2
    assert all("第" in passage for passage in passages)


def test_build_nodes_skips_duplicate_lead_for_short_parent(tmp_path) -> None:
    write_raw_item(tmp_path, kind="answer", source_id="1", body="短回答。")
    parent = load_parent_documents(tmp_path)[0]

    nodes = build_nodes_for_parent(parent)

    assert [node.node_type for node in nodes] == ["title", "passage"]


def test_build_corpus_writes_artifacts(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    index_dir = tmp_path / "index"
    write_raw_item(raw_dir, kind="answer", source_id="1")
    write_raw_item(raw_dir, kind="article", source_id="2")
    write_raw_item(raw_dir, kind="pin", source_id="3")

    result = build_corpus(raw_dir, index_dir)

    assert result.parent_count == 3
    assert result.node_count >= 3
    assert (index_dir / "parents.jsonl").exists()
    assert (index_dir / "nodes.jsonl").exists()
    manifest = json.loads((index_dir / "build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["document_kind_counts"] == {"answer": 1, "article": 1, "pin": 1}


def test_cli_build_writes_default_author_index(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    raw_dir = tmp_path / "data" / "authors" / "zhihu" / "alice" / "raw"
    write_raw_item(raw_dir, kind="answer", source_id="1")

    code = cli.main(["build", "alice"])

    assert code == 0
    index_dir = tmp_path / "data" / "authors" / "zhihu" / "alice" / "index"
    assert (index_dir / "parents.jsonl").exists()
    assert (index_dir / "nodes.jsonl").exists()
