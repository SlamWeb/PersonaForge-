"""Qdrant collection helpers for child-node indexes."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from personaforge.ingest.embeddings import TextEmbedding

COLLECTION_PREFIX = "personaforge"
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "personaforge.local/qdrant-point")


def collection_name_for_author(source: str, author_token: str) -> str:
    source_part = _safe_collection_part(source)
    author_part = _safe_collection_part(author_token)
    return f"{COLLECTION_PREFIX}__{source_part}__{author_part}"


def point_id_for_node(node_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, node_id))


def create_local_client(path: Path):
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency.
        raise RuntimeError(
            "Qdrant indexing requires optional dependency `qdrant-client`. "
            "Install with: pip install -e \".[index]\""
        ) from exc
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def recreate_collection(client: Any, collection_name: str, *, dense_size: int) -> None:
    from qdrant_client import models

    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": models.VectorParams(size=dense_size, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(
                index=models.SparseIndexParams(on_disk=False),
            ),
        },
    )


def make_point(node: dict[str, Any], embedding: TextEmbedding):
    from qdrant_client import models

    node_id = str(node["node_id"])
    payload = {
        "node_id": node_id,
        "parent_id": node["parent_id"],
        "source": node["source"],
        "kind": node["kind"],
        "source_id": node["source_id"],
        "node_type": node["node_type"],
        "title": node["title"],
        "path": node["path"],
        "author_token": node.get("author_token"),
        "index": node["index"],
    }
    return models.PointStruct(
        id=point_id_for_node(node_id),
        vector={
            "dense": embedding.dense,
            "sparse": models.SparseVector(
                indices=embedding.sparse.indices,
                values=embedding.sparse.values,
            ),
        },
        payload=payload,
    )


def upload_points(client: Any, collection_name: str, points: Iterable[Any], *, batch_size: int = 64) -> int:
    batch: list[Any] = []
    total = 0
    for point in points:
        batch.append(point)
        if len(batch) >= batch_size:
            client.upsert(collection_name=collection_name, points=batch)
            total += len(batch)
            batch = []
    if batch:
        client.upsert(collection_name=collection_name, points=batch)
        total += len(batch)
    return total


def _safe_collection_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-_")
    return cleaned or "unknown"
