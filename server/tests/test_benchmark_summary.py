import json
import os
import re
import subprocess
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

import pytest
import run_benchmark as run_benchmark_module

os.environ.setdefault("MODEL_PROXY_URL", "https://placeholder.invalid")
os.environ.setdefault("MODEL_PROXY_API_KEY", "test-key")
os.environ.setdefault("LLM_DEFAULT", "gpt-5-mini")

import benchmark.infrastructure as infra_module

from benchmark.infrastructure import (
    RunTelemetry,
    VirtualFileSystem,
    _build_usage_metadata,
    _update_run_metrics_from_status,
    run_agent_loop,
)
from run_benchmark import (
    _collect_jsonl_token_metrics,
    _collect_run_token_metrics,
    _prepare_model_env,
    _proxy_supports_genai,
    make_llm,
)


class TestRunTelemetry:
    def test_vfs_counts_only_new_files(self):
        metrics = RunTelemetry()
        vfs = VirtualFileSystem()
        vfs.bind_run_metrics(metrics)

        vfs.write("a.py", "print('a')")
        vfs.write("a.py", "print('b')")
        vfs.write("b.py", "print('c')")

        assert metrics.created_files == {"a.py", "b.py"}

    def test_vfs_temp_root_uses_timestamp_name(self):
        vfs = VirtualFileSystem()

        assert re.fullmatch(r"\d{8}-\d{6}-\d{6}(?:-\d+)?", vfs.root.name)  # noqa: SLF001

    def test_activation_steps_record_first_online_iteration(self):
        metrics = RunTelemetry()

        _update_run_metrics_from_status(
            metrics,
            {
                "terminal_ids": ["SYS1", "SYS2"],
                "online_flags": [False, False],
            },
            iteration=0,
        )
        _update_run_metrics_from_status(
            metrics,
            {
                "terminal_ids": ["SYS1", "SYS2"],
                "online_flags": [True, False],
            },
            iteration=5,
        )
        _update_run_metrics_from_status(
            metrics,
            {
                "terminal_ids": ["SYS1", "SYS2"],
                "online_flags": [True, True],
            },
            iteration=9,
        )
        _update_run_metrics_from_status(
            metrics,
            {
                "terminal_ids": ["SYS1", "SYS2"],
                "online_flags": [True, True],
            },
            iteration=12,
        )

        assert metrics.terminal_activation_steps == {
            "SYS1": 5,
            "SYS2": 9,
        }


class TestRunSummary:
    def test_build_usage_metadata_keeps_raw_provider_usage_fields(self):
        class FakeUsage:
            prompt_token_count = 120
            candidates_token_count = 30
            cached_content_token_count = 80
            thoughts_token_count = 11

            def model_dump(self):
                return {
                    "prompt_token_count": self.prompt_token_count,
                    "candidates_token_count": self.candidates_token_count,
                    "cached_content_token_count": self.cached_content_token_count,
                    "thoughts_token_count": self.thoughts_token_count,
                }

        class FakeLlm:
            def _get_usage_meta(self, usage):
                return {
                    "input_tokens": usage.prompt_token_count,
                    "output_tokens": usage.candidates_token_count,
                }

        usage = _build_usage_metadata(FakeLlm(), FakeUsage())

        assert usage == {
            "input_tokens": 120,
            "output_tokens": 30,
            "prompt_token_count": 120,
            "candidates_token_count": 30,
            "cached_content_token_count": 80,
            "thoughts_token_count": 11,
        }

    def test_build_usage_metadata_flattens_openai_cached_tokens(self):
        class FakeUsage:
            prompt_tokens = 120
            completion_tokens = 30

            def model_dump(self):
                return {
                    "prompt_tokens": self.prompt_tokens,
                    "completion_tokens": self.completion_tokens,
                    "prompt_tokens_details": {
                        "cached_tokens": 80,
                        "audio_tokens": 0,
                    },
                    "completion_tokens_details": {
                        "reasoning_tokens": 11,
                    },
                }

        class FakeLlm:
            def _get_usage_meta(self, usage):
                return {
                    "input_tokens": usage.prompt_tokens,
                    "output_tokens": usage.completion_tokens,
                }

        usage = _build_usage_metadata(FakeLlm(), FakeUsage())

        assert usage["input_tokens"] == 120
        assert usage["output_tokens"] == 30
        assert usage["cached_input_tokens"] == 80
        assert usage["reasoning_token_count"] == 11
        assert usage["prompt_tokens_details"] == {
            "cached_tokens": 80,
            "audio_tokens": 0,
        }

    def test_collect_run_token_metrics_sums_all_requests(self, tmp_path: Path):
        run_file = tmp_path / "sample.run.json"
        run_file.write_text(
            json.dumps(
                {
                    "conversations": [
                        {
                            "requests": [
                                {"metrics": {"inputTokens": 10, "outputTokens": 3}},
                                {"metrics": {"inputTokens": 7, "outputTokens": 2}},
                            ]
                        },
                        {
                            "requests": [
                                {"metrics": {"inputTokens": 1}},
                            ]
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert _collect_run_token_metrics(run_file) == {
            "inputTokens": 18,
            "outputTokens": 5,
        }

    def test_collect_jsonl_token_metrics_sums_model_response_usage(self, tmp_path: Path):
        log_file = tmp_path / "sample.jsonl"
        log_file.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {
                                "prompt_token_count": 10,
                                "candidates_token_count": 3,
                                "total_token_count": 13,
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {
                                "prompt_token_count": 7,
                                "candidates_token_count": 2,
                                "total_token_count": 9,
                            },
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        assert _collect_jsonl_token_metrics(log_file) == {
            "prompt_token_count": 17,
            "candidates_token_count": 5,
            "total_token_count": 22,
        }

    def test_effective_total_tokens_supports_input_output_token_keys(self):
        from run_benchmark import _effective_total_tokens

        assert _effective_total_tokens(
            {"input_tokens": 100, "output_tokens": 25}
        ) == 125

    def test_collect_jsonl_token_metrics_skips_malformed_lines(self, tmp_path: Path):
        log_file = tmp_path / "sample.jsonl"
        log_file.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {
                                "prompt_token_count": 10,
                                "total_token_count": 10,
                            },
                        }
                    ),
                    '{"event_type":"tool_result","result":"unterminated',
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {
                                "prompt_token_count": 7,
                                "total_token_count": 9,
                            },
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        assert _collect_jsonl_token_metrics(log_file) == {
            "prompt_token_count": 17,
            "total_token_count": 19,
        }

    def test_collect_jsonl_token_metrics_handles_unicode_line_separator_inside_json(self, tmp_path: Path):
        log_file = tmp_path / "sample.jsonl"
        log_file.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_type": "tool_result",
                            "result": "prefix\u0085suffix",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "event_type": "model_response",
                            "usage_metadata": {
                                "prompt_token_count": 11,
                                "total_token_count": 13,
                            },
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        assert _collect_jsonl_token_metrics(log_file) == {
            "prompt_token_count": 11,
            "total_token_count": 13,
        }

    def test_run_agent_loop_emits_structured_run_summary_without_summary_text(self, monkeypatch):
        class FailingCompletions:
            def create(self, **kwargs):
                raise RuntimeError("context window exceeded")

        class FailingChat:
            def __init__(self):
                self.completions = FailingCompletions()

        class FailingClient:
            def __init__(self):
                self.chat = FailingChat()

        class FailingLlm:
            model = "failing-model"
            client = FailingClient()

            def _get_usage_meta(self, usage):
                return {}

        events = []

        def fake_emit_event(**kwargs):
            events.append(kwargs)
            return kwargs

        monkeypatch.setattr(infra_module, "emit_event", fake_emit_event)
        monkeypatch.setattr(
            infra_module,
            "_get_status",
            lambda server_url: {
                "terminal_ids": ["SYS1", "SYS2", "SYS3"],
                "online_flags": [True, False, False],
                "online": 1,
                "total": 3,
                "done": False,
            },
        )
        monkeypatch.setattr(infra_module.chats, "new", lambda **kwargs: nullcontext())
        monkeypatch.setattr(infra_module.actors.user, "send", lambda message: None)

        run_agent_loop(
            FailingLlm(),
            "http://127.0.0.1:9999",
            "http://127.0.0.1:9999",
            VirtualFileSystem(),
            outer_welcome_message="welcome",
            max_steps=5,
            terminal_spec="sys32",
            seed=42,
        )

        summaries = [event for event in events if event["event_type"] == "run_summary"]
        assert len(summaries) == 1
        summary = summaries[0]
        assert summary["score"] == 1
        assert summary["max_score"] == 3
        assert summary["done"] is False
        assert "summary_text" not in summary


class TestModelEnvPreparation:
    def test_prepare_model_env_requires_env_file(self, tmp_path: Path):
        missing_env = tmp_path / ".env"
        with mock.patch.object(run_benchmark_module, "_DOTENV_PATH", missing_env):
            with mock.patch.dict(os.environ, {}, clear=True):
                with pytest.raises(SystemExit, match=r"\.env file not found"):
                    _prepare_model_env("gemini-2.5-flash")

    def test_prepare_model_env_reads_proxy_from_env_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "MODEL_PROXY_URL=https://generativelanguage.googleapis.com/v1beta/openapi",
                    "MODEL_PROXY_API_KEY=dotenv-key",
                ]
            ),
            encoding="utf-8",
        )

        with mock.patch.object(run_benchmark_module, "_DOTENV_PATH", env_file):
            with mock.patch.dict(os.environ, {}, clear=True):
                _prepare_model_env("gemini-2.5-flash")

                assert os.environ["LLM_DEFAULT"] == "gemini-2.5-flash"
                assert os.environ["MODEL_PROXY_URL"] == "https://generativelanguage.googleapis.com/v1beta/openapi"
                assert os.environ["MODEL_PROXY_API_KEY"] == "dotenv-key"

    def test_prepare_model_env_env_file_overrides_shell_values(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "MODEL_PROXY_URL=https://dotenv.example/v1",
                    "MODEL_PROXY_API_KEY=dotenv-key",
                ]
            ),
            encoding="utf-8",
        )

        with mock.patch.object(run_benchmark_module, "_DOTENV_PATH", env_file):
            with mock.patch.dict(
                os.environ,
                {
                    "MODEL_PROXY_URL": "https://shell.example/v1",
                    "MODEL_PROXY_API_KEY": "shell-key",
                },
                clear=True,
            ):
                _prepare_model_env("gpt-5-mini")

                assert os.environ["MODEL_PROXY_URL"] == "https://dotenv.example/v1"
                assert os.environ["MODEL_PROXY_API_KEY"] == "dotenv-key"


class TestMakeLlm:
    def test_proxy_supports_genai_defaults_true(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _proxy_supports_genai() is True

    def test_proxy_supports_genai_false_values_disable_genai(self):
        for value in ("FALSE", "false", "0", "NO", "OFF"):
            with mock.patch.dict(os.environ, {"MODEL_PROXY_GENAI_SUPPORT": value}, clear=True):
                assert _proxy_supports_genai() is False

    def test_make_llm_uses_genai_proxy_for_gemini_when_enabled(self):
        with mock.patch.dict(
            os.environ,
            {
                "MODEL_PROXY_URL": "https://generativelanguage.googleapis.com/v1beta/openapi",
                "MODEL_PROXY_API_KEY": "test-key",
                "MODEL_PROXY_GENAI_SUPPORT": "TRUE",
            },
            clear=True,
        ):
            with mock.patch("kaggle_benchmarks.kaggle.load_model", return_value="gemini-llm") as load_model_mock:
                llm = make_llm("gemini-2.5-flash")

        assert llm == "gemini-llm"
        load_model_mock.assert_called_once_with(model_name="gemini-2.5-flash", api="genai")

    def test_make_llm_uses_openai_proxy_for_gemini_when_genai_disabled(self):
        with mock.patch.dict(
            os.environ,
            {
                "MODEL_PROXY_URL": "https://litellm.example/v1",
                "MODEL_PROXY_API_KEY": "test-key",
                "MODEL_PROXY_GENAI_SUPPORT": "FALSE",
            },
            clear=True,
        ):
            with mock.patch("kaggle_benchmarks.kaggle.load_model", return_value="gemini-openai-llm") as load_model_mock:
                llm = make_llm("gemini-2.5-flash")

        assert llm == "gemini-openai-llm"
        load_model_mock.assert_called_once_with(model_name="gemini-2.5-flash", api="openai")

    def test_make_llm_uses_openai_proxy_for_non_gemini(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit, match="MODEL_PROXY_URL and MODEL_PROXY_API_KEY are required"):
                make_llm("gpt-5-mini")

        with mock.patch.dict(
            os.environ,
            {
                "MODEL_PROXY_URL": "https://litellm.example/v1",
                "MODEL_PROXY_API_KEY": "test-key",
            },
            clear=True,
        ):
            with mock.patch("kaggle_benchmarks.kaggle.load_model", return_value="openai-llm") as load_model_mock:
                llm = make_llm("gpt-5-mini")

        assert llm == "openai-llm"
        load_model_mock.assert_called_once_with(model_name="gpt-5-mini", api="openai")


