import json

from fastapi.testclient import TestClient

import logs_viewer.app as viewer_module
from logs_viewer.app import app


def _make_client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


class TestViewer:
    def test_viewer_root_is_served(self):
        response = _make_client().get("/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Run Log" in response.text


class TestRunLogsApi:
    def test_run_logs_lists_log_file_summaries(self, tmp_path, monkeypatch):
        log_path = tmp_path / "sample.jsonl"
        log_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "time": "2026-03-30T18:00:00Z",
                            "event_type": "run_start",
                            "model": "gemini-2.0-flash",
                            "terminal_spec": "sys32",
                        }
                    ),
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {"input_tokens": 100, "output_tokens": 23},
                        }
                    ),
                    json.dumps(
                        {
                            "time": "2026-03-30T18:01:00Z",
                            "event_type": "run_end",
                            "score": 1,
                            "max_score": 2,
                        }
                    ),
                    json.dumps(
                        {
                            "time": "2026-03-30T18:01:01Z",
                            "event_type": "validation_summary",
                            "number_of_passed_validating_terminals": 1,
                            "total": 3,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(viewer_module, "_RUN_LOGS_DIR", tmp_path)

        response = _make_client().get("/run-logs")

        assert response.status_code == 200
        run = response.json()["runs"][0]
        assert run["file_name"] == "sample.jsonl"
        assert run["model"] == "gemini-2.0-flash"
        assert run["validation"] == {"passed": 1, "total": 3}
        assert run["total_tokens"] == 123

    def test_run_logs_list_sums_tokens_across_runs_and_uses_last_validation(self, tmp_path, monkeypatch):
        log_path = tmp_path / "sample.jsonl"
        log_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "time": "2026-04-02T01:00:00Z",
                            "event_type": "run_start",
                            "model": "gpt-5-mini",
                            "terminal_spec": "sys32",
                        }
                    ),
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {"input_tokens": 150, "output_tokens": 25},
                        }
                    ),
                    json.dumps({"time": "2026-04-02T01:05:00Z", "event_type": "run_end", "score": 1, "max_score": 2}),
                    json.dumps(
                        {
                            "time": "2026-04-02T01:05:01Z",
                            "event_type": "validation_summary",
                            "number_of_passed_validating_terminals": 1,
                            "total": 3,
                        }
                    ),
                    json.dumps(
                        {
                            "time": "2026-04-02T02:00:00Z",
                            "event_type": "run_start",
                            "model": "gpt-5-mini",
                            "terminal_spec": "hash-sys32",
                        }
                    ),
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {"input_tokens": 10, "output_tokens": 5},
                        }
                    ),
                    json.dumps({"time": "2026-04-02T02:05:00Z", "event_type": "run_end", "score": 2, "max_score": 2}),
                    json.dumps(
                        {
                            "time": "2026-04-02T02:05:01Z",
                            "event_type": "validation_summary",
                            "number_of_passed_validating_terminals": 2,
                            "total": 3,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(viewer_module, "_RUN_LOGS_DIR", tmp_path)

        response = _make_client().get("/run-logs")

        assert response.status_code == 200
        run = response.json()["runs"][0]
        assert run["total_tokens"] == 190
        assert run["validation"] == {"passed": 2, "total": 3}

    def test_run_logs_list_uses_openai_cached_prompt_token_details(self, tmp_path, monkeypatch):
        log_path = tmp_path / "sample.jsonl"
        log_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "time": "2026-04-02T01:00:00Z",
                            "event_type": "run_start",
                            "model": "gpt-5-nano",
                            "terminal_spec": "sys32",
                        }
                    ),
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {
                                "input_tokens": 100,
                                "output_tokens": 23,
                                "prompt_tokens_details": {"cached_tokens": 40},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "time": "2026-04-02T01:01:00Z",
                            "event_type": "run_end",
                            "score": 1,
                            "max_score": 2,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(viewer_module, "_RUN_LOGS_DIR", tmp_path)

        response = _make_client().get("/run-logs")

        assert response.status_code == 200
        run = response.json()["runs"][0]
        assert run["sum_input_tokens"] == 100
        assert run["sum_uncached_input_tokens"] == 60
        assert run["sum_output_tokens"] == 23

    def test_run_log_detail_returns_runs_with_their_own_events(self, tmp_path, monkeypatch):
        log_path = tmp_path / "detail.jsonl"
        log_path.write_text(
            "\n".join(
                [
                    json.dumps({"time": "2026-04-02T01:00:00Z", "event_type": "run_start", "model": "gpt-5-mini", "terminal_spec": "main"}),
                    json.dumps({"event_type": "terminal_input", "terminal_id": "SYS1", "payload": "HELP"}),
                    json.dumps({"time": "2026-04-02T01:00:02Z", "event_type": "run_end", "score": 1, "max_score": 1}),
                    json.dumps({"time": "2026-04-02T01:00:03Z", "event_type": "validation_summary", "number_of_passed_validating_terminals": 1, "total": 1}),
                    json.dumps({"time": "2026-04-02T02:00:00Z", "event_type": "run_start", "model": "gpt-5-mini", "terminal_spec": "hash-main"}),
                    json.dumps({"event_type": "terminal_input", "terminal_id": "SYS1", "payload": "ACT"}),
                    json.dumps({"time": "2026-04-02T02:00:02Z", "event_type": "run_end", "score": 2, "max_score": 2}),
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(viewer_module, "_RUN_LOGS_DIR", tmp_path)

        response = _make_client().get("/run-logs/detail.jsonl")

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["file_name"] == "detail.jsonl"
        assert len(body["runs"]) == 2
        assert body["runs"][0]["summary"]["terminal_spec"] == "main"
        assert body["runs"][0]["summary"]["validation"] == {"passed": 1, "total": 1}
        assert len(body["runs"][0]["events"]) == 4
        assert body["runs"][0]["events"][1]["event_type"] == "terminal_input"

    def test_run_log_detail_handles_unicode_line_separator_inside_event_payload(self, tmp_path, monkeypatch):
        log_path = tmp_path / "detail.jsonl"
        log_path.write_text(
            "\n".join(
                [
                    json.dumps({"time": "2026-04-02T01:00:00Z", "event_type": "run_start", "model": "gpt-5-mini", "terminal_spec": "main"}),
                    json.dumps(
                        {
                            "event_type": "tool_result",
                            "tool_name": "run_python_file",
                            "result": "prefix\u0085suffix",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps({"time": "2026-04-02T01:00:02Z", "event_type": "run_end", "score": 1, "max_score": 1}),
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(viewer_module, "_RUN_LOGS_DIR", tmp_path)

        response = _make_client().get("/run-logs/detail.jsonl")

        assert response.status_code == 200
        body = response.json()
        assert len(body["runs"]) == 1
        assert body["runs"][0]["events"][1]["result"] == "prefix\u0085suffix"

    def test_run_log_detail_rejects_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(viewer_module, "_RUN_LOGS_DIR", tmp_path)

        response = _make_client().get("/run-logs/missing.jsonl")

        assert response.status_code == 404
