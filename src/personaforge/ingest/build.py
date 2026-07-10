"""Build ingest artifacts from a crawler raw corpus."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from personaforge.crawler.models import utc_now_iso
from personaforge.crawler.storage import write_jsonl
from personaforge.ingest.loader import load_parent_documents
from personaforge.ingest.nodes import build_nodes

BuildQuality = Literal["fast", "full"]


@dataclass(slots=True)
class BuildResult:
    raw_dir: Path
    index_dir: Path
    quality: BuildQuality
    parent_count: int
    node_count: int
    node_type_counts: dict[str, int]
    document_kind_counts: dict[str, int]
    parents_path: Path
    nodes_path: Path
    manifest_path: Path


def build_corpus(raw_dir: Path, index_dir: Path, *, quality: BuildQuality = "fast") -> BuildResult:
    if quality != "fast":
        raise NotImplementedError("`--quality full` is reserved for later summary nodes.")

    parents = load_parent_documents(raw_dir)
    nodes = build_nodes(parents)

    index_dir.mkdir(parents=True, exist_ok=True)
    parents_path = index_dir / "parents.jsonl"
    nodes_path = index_dir / "nodes.jsonl"
    manifest_path = index_dir / "build_manifest.json"

    write_jsonl(parents, parents_path, append=False)
    write_jsonl(nodes, nodes_path, append=False)

    node_type_counts = dict(Counter(node.node_type for node in nodes))
    document_kind_counts = dict(Counter(parent.kind for parent in parents))
    manifest = {
        "built_at": utc_now_iso(),
        "quality": quality,
        "raw_dir": str(raw_dir),
        "index_dir": str(index_dir),
        "parent_count": len(parents),
        "node_count": len(nodes),
        "node_type_counts": node_type_counts,
        "document_kind_counts": document_kind_counts,
        "artifacts": {
            "parents": parents_path.name,
            "nodes": nodes_path.name,
            "manifest": manifest_path.name,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return BuildResult(
        raw_dir=raw_dir,
        index_dir=index_dir,
        quality=quality,
        parent_count=len(parents),
        node_count=len(nodes),
        node_type_counts=node_type_counts,
        document_kind_counts=document_kind_counts,
        parents_path=parents_path,
        nodes_path=nodes_path,
        manifest_path=manifest_path,
    )


def build_result_to_dict(result: BuildResult) -> dict[str, object]:
    value = asdict(result)
    for key in ("raw_dir", "index_dir", "parents_path", "nodes_path", "manifest_path"):
        value[key] = str(value[key])
    return value

