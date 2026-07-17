from __future__ import annotations

from personaforge.web.trace import estimated_usage_for_text, read_trace, write_trace


def test_trace_retention_keeps_newest_normal_web_runs(tmp_path) -> None:
    for index in range(3):
        trace_id = f"trace-20260714-00000{index}-abcdefgh"
        write_trace(
            tmp_path,
            "alice",
            trace_id,
            {"trace_id": trace_id, "status": "completed"},
            retention=2,
        )

    trace_dir = tmp_path / "authors" / "zhihu" / "alice" / "traces"
    traces = sorted(path.name for path in trace_dir.glob("*.json"))

    assert len(traces) == 2
    assert "trace-20260714-000002-abcdefgh.json" in traces
    assert read_trace(tmp_path, "alice", "trace-20260714-000002-abcdefgh")["status"] == "completed"


def test_estimated_usage_is_explicitly_labelled() -> None:
    usage = estimated_usage_for_text("中文文本", "plain text")

    assert usage["source"] == "estimated"
    assert usage["estimated_tokens"] > 0
    assert "note" in usage
