"""Retrieve parent documents from a Qdrant child-node index."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from personaforge.ingest.embeddings import BgeM3Encoder, TextEncoder
from personaforge.ingest.query_understanding import RetrievalQuery
from personaforge.ingest.qdrant_index import collection_name_for_author, create_local_client


@dataclass(slots=True)
class ChildHit:
    rank: int
    score: float
    node_id: str
    parent_id: str
    node_type: str
    title: str
    path: str
    route: str


@dataclass(slots=True)
class ParentHit:
    rank: int
    parent_id: str
    score: float
    title: str
    path: str
    first_hits: list[ChildHit] = field(default_factory=list)
    parent: dict[str, Any] | None = None


@dataclass(slots=True)
class RetrieveResult:
    query: str
    collection_name: str
    child_top_k: int
    parent_top_k: int
    routes: dict[str, list[ChildHit]]
    parents: list[ParentHit]
    retrieval_queries: list[RetrievalQuery] = field(default_factory=list)


def retrieve_parents(
    query: str,
    *,
    author: str,
    index_dir: Path,
    qdrant_path: Path | None = None,
    encoder: TextEncoder | None = None,
    source: str = "zhihu",
    child_top_k: int = 100,
    parent_top_k: int = 20,
    rrf_k: int = 60,
) -> RetrieveResult:
    collection_name = collection_name_for_author(source, author)
    qdrant_path = qdrant_path or index_dir / "qdrant"
    client = create_local_client(qdrant_path)
    encoder = encoder or BgeM3Encoder()
    embedding = encoder.encode_texts([query], batch_size=1)[0]

    dense_hits = query_child_nodes(
        client,
        collection_name,
        query_vector=embedding.dense,
        route="dense",
        child_top_k=child_top_k,
    )
    sparse_hits = query_child_nodes(
        client,
        collection_name,
        query_vector={
            "indices": embedding.sparse.indices,
            "values": embedding.sparse.values,
        },
        route="sparse",
        child_top_k=child_top_k,
    )

    routes = {"dense": dense_hits, "sparse": sparse_hits}
    parent_hits = fuse_parent_hits(routes, rrf_k=rrf_k, parent_top_k=parent_top_k)
    parents_by_id = load_parents(index_dir / "parents.jsonl")
    for hit in parent_hits:
        hit.parent = parents_by_id.get(hit.parent_id)

    client.close()
    return RetrieveResult(
        query=query,
        collection_name=collection_name,
        child_top_k=child_top_k,
        parent_top_k=parent_top_k,
        routes=routes,
        parents=parent_hits,
        retrieval_queries=[RetrievalQuery(route="original_semantics", query=query)],
    )


def retrieve_parents_for_queries(
    query: str,
    retrieval_queries: list[RetrievalQuery],
    *,
    author: str,
    index_dir: Path,
    qdrant_path: Path | None = None,
    encoder: TextEncoder | None = None,
    source: str = "zhihu",
    child_top_k: int = 100,
    per_query_parent_k: int = 30,
    parent_top_k: int = 20,
    rrf_k: int = 60,
) -> RetrieveResult:
    collection_name = collection_name_for_author(source, author)
    qdrant_path = qdrant_path or index_dir / "qdrant"
    client = create_local_client(qdrant_path)
    encoder = encoder or BgeM3Encoder()

    child_routes: dict[str, list[ChildHit]] = {}
    parent_routes: dict[str, list[ParentHit]] = {}
    for retrieval_query in retrieval_queries:
        embedding = encoder.encode_texts([retrieval_query.query], batch_size=1)[0]
        dense_route = f"{retrieval_query.route}:dense"
        sparse_route = f"{retrieval_query.route}:sparse"
        dense_hits = query_child_nodes(
            client,
            collection_name,
            query_vector=embedding.dense,
            route=dense_route,
            vector_name="dense",
            child_top_k=child_top_k,
        )
        sparse_hits = query_child_nodes(
            client,
            collection_name,
            query_vector={
                "indices": embedding.sparse.indices,
                "values": embedding.sparse.values,
            },
            route=sparse_route,
            vector_name="sparse",
            child_top_k=child_top_k,
        )
        child_routes[dense_route] = dense_hits
        child_routes[sparse_route] = sparse_hits
        parent_routes[retrieval_query.route] = fuse_parent_hits(
            {dense_route: dense_hits, sparse_route: sparse_hits},
            rrf_k=rrf_k,
            parent_top_k=per_query_parent_k,
        )

    parent_hits = fuse_parent_rankings(parent_routes, rrf_k=rrf_k, parent_top_k=parent_top_k)
    parents_by_id = load_parents(index_dir / "parents.jsonl")
    for hit in parent_hits:
        hit.parent = parents_by_id.get(hit.parent_id)

    client.close()
    return RetrieveResult(
        query=query,
        collection_name=collection_name,
        child_top_k=child_top_k,
        parent_top_k=parent_top_k,
        routes=child_routes,
        parents=parent_hits,
        retrieval_queries=retrieval_queries,
    )


def query_child_nodes(
    client: Any,
    collection_name: str,
    *,
    query_vector: Any,
    route: str,
    vector_name: str | None = None,
    child_top_k: int,
) -> list[ChildHit]:
    using = vector_name or route
    if using == "sparse" and isinstance(query_vector, dict):
        try:
            from qdrant_client import models
        except ImportError:
            # Unit tests can use fake clients without installing the optional
            # qdrant-client dependency.
            pass
        else:
            query_vector = models.SparseVector(
                indices=query_vector["indices"],
                values=query_vector["values"],
            )

    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        using=using,
        limit=child_top_k,
        with_payload=True,
        with_vectors=False,
    )
    points = getattr(response, "points", response)
    hits: list[ChildHit] = []
    for index, point in enumerate(points, start=1):
        payload = point.payload or {}
        hits.append(
            ChildHit(
                rank=index,
                score=float(point.score),
                node_id=str(payload.get("node_id", "")),
                parent_id=str(payload.get("parent_id", "")),
                node_type=str(payload.get("node_type", "")),
                title=str(payload.get("title", "")),
                path=str(payload.get("path", "")),
                route=route,
            )
        )
    return hits


def fuse_parent_hits(
    routes: dict[str, list[ChildHit]],
    *,
    rrf_k: int = 60,
    parent_top_k: int = 20,
) -> list[ParentHit]:
    scores: dict[str, float] = {}
    first_hits: dict[str, list[ChildHit]] = {}
    display: dict[str, ChildHit] = {}

    for hits in routes.values():
        seen_in_route: set[str] = set()
        for hit in hits:
            if not hit.parent_id or hit.parent_id in seen_in_route:
                continue
            seen_in_route.add(hit.parent_id)
            scores[hit.parent_id] = scores.get(hit.parent_id, 0.0) + 1.0 / (rrf_k + hit.rank)
            first_hits.setdefault(hit.parent_id, []).append(hit)
            display.setdefault(hit.parent_id, hit)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:parent_top_k]
    return [
        ParentHit(
            rank=index,
            parent_id=parent_id,
            score=score,
            title=display[parent_id].title,
            path=display[parent_id].path,
            first_hits=first_hits[parent_id],
        )
        for index, (parent_id, score) in enumerate(ranked, start=1)
    ]


def fuse_parent_rankings(
    routes: dict[str, list[ParentHit]],
    *,
    rrf_k: int = 60,
    parent_top_k: int = 20,
) -> list[ParentHit]:
    scores: dict[str, float] = {}
    first_hits: dict[str, list[ChildHit]] = {}
    display: dict[str, ParentHit] = {}

    for parent_hits in routes.values():
        seen_in_route: set[str] = set()
        for hit in parent_hits:
            if not hit.parent_id or hit.parent_id in seen_in_route:
                continue
            seen_in_route.add(hit.parent_id)
            scores[hit.parent_id] = scores.get(hit.parent_id, 0.0) + 1.0 / (rrf_k + hit.rank)
            first_hits.setdefault(hit.parent_id, []).extend(hit.first_hits)
            display.setdefault(hit.parent_id, hit)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:parent_top_k]
    return [
        ParentHit(
            rank=index,
            parent_id=parent_id,
            score=score,
            title=display[parent_id].title,
            path=display[parent_id].path,
            first_hits=first_hits[parent_id],
        )
        for index, (parent_id, score) in enumerate(ranked, start=1)
    ]


def load_parents(path: Path) -> dict[str, dict[str, Any]]:
    parents: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        parents[str(row["doc_id"])] = row
    return parents
