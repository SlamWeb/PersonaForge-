"""Convert parent documents into retrieval child nodes."""

from __future__ import annotations

from personaforge.ingest.chunking import build_lead, build_passages, normalize_for_compare
from personaforge.ingest.models import ChildNode, ParentDocument


def build_nodes_for_parent(parent: ParentDocument) -> list[ChildNode]:
    nodes: list[ChildNode] = []

    if parent.title.strip():
        nodes.append(_make_node(parent, node_type="title", text=parent.title.strip(), index=0))

    passages = build_passages(parent.text)
    lead = build_lead(parent.text)
    if lead and not _lead_duplicates_single_passage(lead, passages):
        nodes.append(_make_node(parent, node_type="lead", text=lead, index=0))

    for index, passage in enumerate(passages):
        nodes.append(_make_node(parent, node_type="passage", text=passage, index=index))

    return nodes


def build_nodes(parents: list[ParentDocument]) -> list[ChildNode]:
    nodes: list[ChildNode] = []
    for parent in parents:
        nodes.extend(build_nodes_for_parent(parent))
    return nodes


def _make_node(parent: ParentDocument, *, node_type: str, text: str, index: int) -> ChildNode:
    node_id = f"{parent.doc_id}:{node_type}:{index}"
    return ChildNode(
        node_id=node_id,
        parent_id=parent.doc_id,
        node_type=node_type,  # type: ignore[arg-type]
        text=text,
        source=parent.source,
        kind=parent.kind,
        source_id=parent.source_id,
        title=parent.title,
        path=parent.path,
        author_token=parent.author_token,
        index=index,
    )


def _lead_duplicates_single_passage(lead: str, passages: list[str]) -> bool:
    return len(passages) == 1 and normalize_for_compare(lead) == normalize_for_compare(passages[0])
