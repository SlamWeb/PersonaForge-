"""Data models for ingest artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DocumentKind = Literal["answer", "article", "pin"]
NodeKind = Literal["title", "lead", "passage"]


@dataclass(slots=True)
class ParentDocument:
    doc_id: str
    source: str
    kind: DocumentKind
    source_id: str
    title: str
    text: str
    path: str
    author_token: str | None = None
    url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    fetched_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class ChildNode:
    node_id: str
    parent_id: str
    node_type: NodeKind
    text: str
    source: str
    kind: DocumentKind
    source_id: str
    title: str
    path: str
    author_token: str | None = None
    index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
