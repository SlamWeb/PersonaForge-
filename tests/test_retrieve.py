from __future__ import annotations

import json

from personaforge.ingest.embeddings import SparseEmbedding, TextEmbedding
from personaforge.ingest.query_understanding import RetrievalQuery
from personaforge.ingest.retrieve import retrieve_parents_for_queries


class FakeEncoder:
    def encode_texts(self, texts: list[str], *, batch_size: int = 1) -> list[TextEmbedding]:
        return [
            TextEmbedding(
                dense=[1.0, float(len(text))],
                sparse=SparseEmbedding(indices=[len(text)], values=[1.0]),
            )
            for text in texts
        ]


class FakePoint:
    def __init__(self, score: float, payload: dict[str, str]):
        self.score = score
        self.payload = payload


class FakeResponse:
    def __init__(self, points):
        self.points = points


class FakeClient:
    def __init__(self):
        self.calls = []

    def query_points(self, *, collection_name, query, using, limit, with_payload, with_vectors):
        self.calls.append(using)
        if using == "dense":
            points = [
                _point("zhihu:answer:1", "title", 0.90),
                _point("zhihu:answer:2", "passage", 0.80),
            ]
        else:
            points = [
                _point("zhihu:answer:2", "title", 0.95),
                _point("zhihu:answer:3", "passage", 0.70),
            ]
        return FakeResponse(points[:limit])

    def close(self):
        return None


def _point(parent_id: str, node_type: str, score: float) -> FakePoint:
    source_id = parent_id.rsplit(":", 1)[-1]
    return FakePoint(
        score,
        {
            "node_id": f"{parent_id}:{node_type}:0",
            "parent_id": parent_id,
            "node_type": node_type,
            "title": f"标题{source_id}",
            "path": f"answer/answer-{source_id}.md",
        },
    )


def test_retrieve_parents_for_queries_uses_dense_sparse_per_query_and_final_parent_topk(monkeypatch, tmp_path):
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    parents = [
        {"doc_id": "zhihu:answer:1", "title": "标题1", "text": "正文1"},
        {"doc_id": "zhihu:answer:2", "title": "标题2", "text": "正文2"},
        {"doc_id": "zhihu:answer:3", "title": "标题3", "text": "正文3"},
    ]
    (index_dir / "parents.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in parents),
        encoding="utf-8",
        newline="\n",
    )
    fake_client = FakeClient()
    monkeypatch.setattr("personaforge.ingest.retrieve.create_local_client", lambda path: fake_client)

    result = retrieve_parents_for_queries(
        "原问题",
        [
            RetrievalQuery(route="original_semantics", query="原问题"),
            RetrievalQuery(route="conceptual_values", query="抽象概念"),
        ],
        author="alice",
        index_dir=index_dir,
        qdrant_path=tmp_path / "qdrant",
        encoder=FakeEncoder(),
        child_top_k=2,
        per_query_parent_k=3,
        parent_top_k=2,
    )

    assert fake_client.calls == ["dense", "sparse", "dense", "sparse"]
    assert len(result.parents) == 2
    assert result.parents[0].parent_id == "zhihu:answer:2"
    assert result.parents[0].parent is not None
    assert set(result.routes) == {
        "original_semantics:dense",
        "original_semantics:sparse",
        "conceptual_values:dense",
        "conceptual_values:sparse",
    }
