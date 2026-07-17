"""Build strict temporal holdouts from existing parent documents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET_SCHEMA_VERSION = "personaforge.eval.dataset.v0"


@dataclass(frozen=True, slots=True)
class TemporalDatasetResult:
    dataset_path: Path
    manifest_path: Path
    cutoff: str
    dev_count: int
    test_count: int
    excluded_parent_count: int


def prepare_temporal_dataset(
    *,
    author: str,
    index_dir: Path,
    out_dir: Path,
    dev_size: int = 10,
    test_size: int = 20,
    min_answer_characters: int = 200,
) -> TemporalDatasetResult:
    if dev_size < 1 or test_size < 1:
        raise ValueError("dev_size and test_size must both be positive.")

    parents = load_jsonl(index_dir / "parents.jsonl")
    eligible = sorted(
        (
            row
            for row in parents
            if is_eligible_answer(row, min_answer_characters=min_answer_characters)
        ),
        key=created_at_key,
    )
    required_count = dev_size + test_size
    if len(eligible) < required_count:
        raise ValueError(
            f"Need {required_count} eligible answers, but only found {len(eligible)} in {index_dir}."
        )

    holdout = eligible[-required_count:]
    dev_rows = holdout[:dev_size]
    test_rows = holdout[dev_size:]
    cutoff = str(dev_rows[0]["created_at"])
    cutoff_time = parse_datetime(cutoff)
    excluded_parent_ids = sorted(
        str(row.get("doc_id"))
        for row in parents
        if should_exclude_from_train(row, cutoff_time)
    )

    records = [
        *[
            make_dataset_item(row, split="dev", ordinal=index)
            for index, row in enumerate(dev_rows, start=1)
        ],
        *[
            make_dataset_item(row, split="test", ordinal=index)
            for index, row in enumerate(test_rows, start=1)
        ],
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "dataset.jsonl"
    manifest_path = out_dir / "dataset_manifest.json"
    write_jsonl(records, dataset_path)
    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "author": author,
        "source_index_dir": str(index_dir),
        "source_parents_sha256": sha256_json(parents),
        "dataset_sha256": sha256_json(records),
        "created_at": utc_now(),
        "selection": {
            "kind": "answer",
            "min_answer_characters": min_answer_characters,
            "dev_size": dev_size,
            "test_size": test_size,
            "temporal_cutoff": cutoff,
            "strict_future_exclusion": True,
        },
        "excluded_parent_ids": excluded_parent_ids,
        "excluded_parent_ids_sha256": sha256_json(excluded_parent_ids),
        "counts": {
            "all_parents": len(parents),
            "eligible_answers": len(eligible),
            "train_parents": len(parents) - len(excluded_parent_ids),
            "excluded_parents": len(excluded_parent_ids),
            "dev": len(dev_rows),
            "test": len(test_rows),
        },
    }
    write_json(manifest, manifest_path)
    return TemporalDatasetResult(
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        cutoff=cutoff,
        dev_count=len(dev_rows),
        test_count=len(test_rows),
        excluded_parent_count=len(excluded_parent_ids),
    )


def load_dataset(path: Path) -> list[dict[str, Any]]:
    return load_jsonl(path)


def load_dataset_manifest(dataset_path: Path) -> dict[str, Any]:
    return read_json(dataset_path.with_name("dataset_manifest.json"))


def is_eligible_answer(row: dict[str, Any], *, min_answer_characters: int) -> bool:
    return bool(
        row.get("kind") == "answer"
        and str(row.get("title") or "").strip()
        and str(row.get("text") or "").strip()
        and len(str(row.get("text") or "").strip()) >= min_answer_characters
        and parse_datetime(str(row.get("created_at") or "")) is not None
    )


def should_exclude_from_train(row: dict[str, Any], cutoff: datetime | None) -> bool:
    created_at = parse_datetime(str(row.get("created_at") or ""))
    return created_at is None or cutoff is None or created_at >= cutoff


def make_dataset_item(row: dict[str, Any], *, split: str, ordinal: int) -> dict[str, Any]:
    return {
        "item_id": f"{split}-{ordinal:02d}",
        "split": split,
        "parent_id": str(row["doc_id"]),
        "query": str(row["title"]),
        "gold_answer": str(row["text"]),
        "created_at": str(row["created_at"]),
        "source_path": str(row.get("path") or ""),
    }


def created_at_key(row: dict[str, Any]) -> datetime:
    value = parse_datetime(str(row.get("created_at") or ""))
    if value is None:
        raise ValueError(f"Missing created_at: {row.get('doc_id')}")
    return value


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSONL file: {path}")
    return [
        row
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
        if isinstance(row, dict)
    ]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    return value


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(value: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> str:
    return datetime.now().astimezone().isoformat()
