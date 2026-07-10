"""Load crawler Markdown files into parent documents."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from personaforge.ingest.models import ParentDocument

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TOP_HEADING_RE = re.compile(r"\A\s*#\s+(.+?)\s*(?:\n+|\Z)", re.DOTALL)
KNOWN_FRONT_MATTER_KEYS = {
    "source",
    "kind",
    "id",
    "title",
    "url",
    "author_token",
    "created_at",
    "updated_at",
    "fetched_at",
}


def load_parent_documents(raw_dir: Path) -> list[ParentDocument]:
    """Read a crawler raw directory and return parent documents."""
    raw_dir = raw_dir.resolve()
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw directory does not exist: {raw_dir}")

    paths = _manifest_paths(raw_dir)
    if not paths:
        paths = sorted(path for path in raw_dir.rglob("*.md") if path.is_file())

    parents: list[ParentDocument] = []
    seen_doc_ids: set[str] = set()
    for path in paths:
        parent = load_parent_document(path, raw_root=raw_dir)
        if parent.doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(parent.doc_id)
        parents.append(parent)
    return parents


def load_parent_document(path: Path, *, raw_root: Path | None = None) -> ParentDocument:
    """Parse one Markdown file into a parent document."""
    text = path.read_text(encoding="utf-8")
    front_matter, markdown_body = split_front_matter(text)
    title, body = split_top_heading(markdown_body)

    source = str(front_matter.get("source") or "unknown")
    kind = str(front_matter.get("kind") or _kind_from_filename(path))
    source_id = str(front_matter.get("id") or path.stem)
    resolved_title = str(front_matter.get("title") or title or path.stem)
    doc_id = f"{source}:{kind}:{source_id}"
    relative_path = path.relative_to(raw_root).as_posix() if raw_root else path.as_posix()
    metadata = {
        key: value
        for key, value in front_matter.items()
        if key not in KNOWN_FRONT_MATTER_KEYS
    }

    return ParentDocument(
        doc_id=doc_id,
        source=source,
        kind=kind,  # type: ignore[arg-type]
        source_id=source_id,
        title=resolved_title,
        text=body.strip(),
        path=relative_path,
        author_token=_optional_str(front_matter.get("author_token")),
        url=_optional_str(front_matter.get("url")),
        created_at=_optional_str(front_matter.get("created_at")),
        updated_at=_optional_str(front_matter.get("updated_at")),
        fetched_at=_optional_str(front_matter.get("fetched_at")),
        metadata=metadata,
    )


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    return parse_front_matter(match.group(1)), text[match.end() :]


def parse_front_matter(value: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        result[key.strip()] = parse_scalar(raw_value.strip())
    return result


def parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return _unescape_quoted(value[1:-1])
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def split_top_heading(markdown_body: str) -> tuple[str | None, str]:
    match = TOP_HEADING_RE.match(markdown_body)
    if not match:
        return None, markdown_body
    return match.group(1).strip(), markdown_body[match.end() :]


def _manifest_paths(raw_dir: Path) -> list[Path]:
    manifest_path = raw_dir / "manifest.jsonl"
    if not manifest_path.exists():
        return []

    paths: list[Path] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        path_value = row.get("path")
        if path_value:
            candidate = raw_dir / str(path_value)
        else:
            candidate = _find_legacy_markdown(raw_dir, row)
        if candidate and candidate.exists():
            paths.append(candidate)
    return paths


def _find_legacy_markdown(raw_dir: Path, row: dict[str, Any]) -> Path | None:
    kind = row.get("kind")
    source_id = row.get("id")
    if not kind or not source_id:
        return None
    matches = sorted(raw_dir.glob(f"{kind}-{source_id}-*.md"))
    return matches[0] if matches else None


def _kind_from_filename(path: Path) -> str:
    prefix = path.name.split("-", 1)[0]
    if prefix in {"answer", "article", "pin"}:
        return prefix
    return "answer"


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _unescape_quoted(value: str) -> str:
    return value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

