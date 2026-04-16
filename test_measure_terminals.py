import json

from measure_terminals import (
    _aggregate_jsonl_metrics,
    _default_csv_path,
    _effective_input_tokens,
    _effective_output_tokens,
    _effective_uncached_input_tokens,
    TerminalMeasurement,
    append_csv_row,
)


def test_aggregate_jsonl_metrics_sums_all_agent_runs(tmp_path):
    log_file = tmp_path / "adaptive.jsonl"
    events = [
        {"event_type": "run_summary", "iterations": 3},
        {"event_type": "model_response", "usage_metadata": {"input_tokens": 10, "output_tokens": 4}},
        {"event_type": "run_summary", "iterations": 7},
        {"event_type": "model_response", "usage_metadata": {"input_tokens": 5, "cached_input_tokens": 2}},
        {"event_type": "model_response", "usage_metadata": {"candidates_token_count": 6}},
    ]
    log_file.write_text(
        "\n".join(json.dumps(event) for event in events),
        encoding="utf-8",
    )

    iterations, token_metrics = _aggregate_jsonl_metrics(log_file)

    assert iterations == 10
    assert token_metrics == {
        "input_tokens": 15,
        "output_tokens": 4,
        "cached_input_tokens": 2,
        "candidates_token_count": 6,
    }
    assert _effective_input_tokens(token_metrics) == 15
    assert _effective_uncached_input_tokens(token_metrics) == 13
    assert _effective_output_tokens(token_metrics) == 4


def test_default_csv_path_is_mode_specific():
    assert _default_csv_path("solve").as_posix() == "logs/measure-terminals/solve.csv"
    assert (
        _default_csv_path("adaptive-learning").as_posix()
        == "logs/measure-terminals/adaptive-learning.csv"
    )


def test_append_csv_row_writes_immediately_and_preserves_existing_rows(tmp_path):
    csv_path = tmp_path / "results.csv"
    first = TerminalMeasurement(
        started_at="2026-04-14T18:00:00",
        model="model-a",
        mode="solve",
        terminal="sys32",
        solved=True,
        iterations=3,
        output_tokens=10,
        input_tokens=20,
        input_uncached_tokens=18,
    )
    second = TerminalMeasurement(
        started_at="2026-04-14T18:00:01",
        model="model-a",
        mode="adaptive-learning",
        terminal="maze",
        solved=False,
        iterations=9,
        output_tokens=30,
        input_tokens=40,
        input_uncached_tokens=35,
    )

    append_csv_row(csv_path, first)
    first_snapshot = csv_path.read_text(encoding="utf-8")
    append_csv_row(csv_path, second)
    final_snapshot = csv_path.read_text(encoding="utf-8")

    assert "model-a,solve,sys32,True,3,10,20,18" in first_snapshot
    assert "model-a,solve,sys32,True,3,10,20,18" in final_snapshot
    assert "model-a,adaptive-learning,maze,False,9,30,40,35" in final_snapshot
    assert final_snapshot.count("started_at,model,mode,terminal,solved,iterations,output_tokens,input_tokens,input_uncached_tokens") == 1
