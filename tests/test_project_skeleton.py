from __future__ import annotations

import json
from pathlib import Path

from personaforge import __version__
from personaforge.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_package_has_version() -> None:
    assert __version__


def test_cli_help_runs(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "PersonaForge" in output


def test_sample_corpus_shape() -> None:
    sample_dir = ROOT / "samples" / "zhihu_mock_md"
    assert sample_dir.exists()

    profile = json.loads((sample_dir / "profile.json").read_text(encoding="utf-8"))
    assert profile["author_token"] == "mock-columnist"

    markdown_files = sorted(sample_dir.rglob("*.md"))
    assert len(markdown_files) >= 10
    assert any(path.name.startswith("answer-") for path in markdown_files)
    assert any(path.name.startswith("article-") for path in markdown_files)
    assert any(path.name.startswith("pin-") for path in markdown_files)

    first = markdown_files[0].read_text(encoding="utf-8")
    assert first.startswith("---\n")
    assert "author_token: \"mock-columnist\"" in first
