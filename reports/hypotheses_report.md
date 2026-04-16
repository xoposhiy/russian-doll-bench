# Log Hypotheses Report

Source: top-level `*.jsonl` files directly in `logs`.

## H1: Creating infrastructure is harder than just solving the task

Among episodes where the current training chain is solved (`run_end.done=true`), count how often validation still does not reach the next 50-task generator boundary. Example: if validation was 50/500 before the run, success means reaching at least 100/500 after the run.

| model | episodes_solved_chain | episodes_solved_chain_but_validation_failed | rate |
| --- | --- | --- | --- |
| gpt-5.4-mini-2026-03-17 | 3 | 3 | 100.0% |
| claude-opus-4-7 | 9 | 6 | 66.7% |
| gemini-2.5-flash | 6 | 4 | 66.7% |
| anthropic/claude-haiku-4-5@20251001 | 11 | 7 | 63.6% |
| deepseek-ai/deepseek-v3.2 | 8 | 5 | 62.5% |
| gemini-3-flash-preview | 31 | 18 | 58.1% |
| gpt-5.4-2026-03-05 | 26 | 13 | 50.0% |
| gemma-4-31b | 20 | 9 | 45.0% |
| zai/glm-5 | 10 | 4 | 40.0% |
| anthropic/claude-opus-4-6@default | 8 | 1 | 12.5% |
| anthropic/claude-sonnet-4-6@default | 7 | 0 | 0.0% |
| gemini-3.1-pro-preview | 5 | 0 | 0.0% |

## H2: Models ignore existing infrastructure, focusing on resolving a task from scratch

Among episodes that start after `main.py` already exists from an earlier episode, count how often the model never reads or explicitly references `main.py`.

| model | episodes_with_preexisting_main_py | episodes_without_main_py_read | rate |
| --- | --- | --- | --- |
| gemini-3.1-flash-lite-preview | 2 | 2 | 100.0% |
| gemma-4-31b | 21 | 18 | 85.7% |
| gemini-2.5-flash | 6 | 3 | 50.0% |
| gpt-5.4-mini-2026-03-17 | 8 | 4 | 50.0% |
| gemini-3-flash-preview | 30 | 5 | 16.7% |
| anthropic/claude-haiku-4-5@20251001 | 10 | 0 | 0.0% |
| anthropic/claude-opus-4-6@default | 7 | 0 | 0.0% |
| anthropic/claude-sonnet-4-6@default | 6 | 0 | 0.0% |
| claude-opus-4-7 | 8 | 0 | 0.0% |
| deepseek-ai/deepseek-v3.2 | 7 | 0 | 0.0% |
| gemini-3.1-pro-preview | 4 | 0 | 0.0% |
| gpt-5.4-2026-03-05 | 32 | 0 | 0.0% |
| zai/glm-5 | 11 | 0 | 0.0% |

## H3: Models do not explore the working directory early

Count episodes with no `ls` subcommand inside the first 3 agent iterations. `run` commands split on `&&`, `;`, and `||`.

| model | episodes_total | episodes_without_ls_in_first_3_iterations | rate |
| --- | --- | --- | --- |
| gemini-3.1-flash-lite-preview | 5 | 5 | 100.0% |
| gemma-4-31b | 23 | 21 | 91.3% |
| gemini-2.5-flash | 7 | 5 | 71.4% |
| gpt-5.4-mini-2026-03-17 | 10 | 4 | 40.0% |
| gemini-3-flash-preview | 33 | 7 | 21.2% |
| anthropic/claude-haiku-4-5@20251001 | 11 | 2 | 18.2% |
| anthropic/claude-opus-4-6@default | 8 | 0 | 0.0% |
| anthropic/claude-sonnet-4-6@default | 7 | 0 | 0.0% |
| claude-opus-4-7 | 9 | 0 | 0.0% |
| deepseek-ai/deepseek-v3.2 | 8 | 0 | 0.0% |
| gemini-3.1-pro-preview | 5 | 0 | 0.0% |
| gpt-5.4-2026-03-05 | 35 | 0 | 0.0% |
| zai/glm-5 | 12 | 0 | 0.0% |

## H4: Models forget to update main.py

Among episodes where all terminals were activated (`run_summary.activated_terminals_count == run_summary.total_terminals`), count how often `main.py` is neither created nor updated during the episode. Episodes that failed to activate the full terminal set are excluded.

| model | episodes_with_all_terminals_activated | episodes_without_main_py_update | rate |
| --- | --- | --- | --- |
| claude-opus-4-7 | 9 | 6 | 66.7% |
| gpt-5.4-mini-2026-03-17 | 3 | 1 | 33.3% |
| gemini-3-flash-preview | 31 | 7 | 22.6% |
| gpt-5.4-2026-03-05 | 26 | 4 | 15.4% |
| gemma-4-31b | 21 | 3 | 14.3% |
| anthropic/claude-opus-4-6@default | 8 | 1 | 12.5% |
| anthropic/claude-haiku-4-5@20251001 | 11 | 0 | 0.0% |
| anthropic/claude-sonnet-4-6@default | 7 | 0 | 0.0% |
| deepseek-ai/deepseek-v3.2 | 8 | 0 | 0.0% |
| gemini-2.5-flash | 6 | 0 | 0.0% |
| gemini-3.1-pro-preview | 5 | 0 | 0.0% |
| zai/glm-5 | 10 | 0 | 0.0% |
| gemini-3.1-flash-lite-preview | 0 | 0 | - |

## H5: Models almost never create non-Python files

List every created file that is not `*.py`.

| model | created_files_total | non_python_files_list |
| --- | --- | --- |
| anthropic/claude-haiku-4-5@20251001 | 3 | KNOWLEDGE_BASE.md |
| anthropic/claude-opus-4-6@default | 32 | knowledge.md |
| anthropic/claude-sonnet-4-6@default | 14 | knowledge.md |
| claude-opus-4-7 | 3 | NOTES.md |
| deepseek-ai/deepseek-v3.2 | 37 | - |
| gemini-2.5-flash | 6 | - |
| gemini-3-flash-preview | 110 | - |
| gemini-3.1-flash-lite-preview | 1 | - |
| gemini-3.1-pro-preview | 10 | - |
| gemma-4-31b | 99 | - |
| gpt-5.4-2026-03-05 | 12 | knowledge.txt, notes.txt, state_probe.txt |
| gpt-5.4-mini-2026-03-17 | 1 | - |
| zai/glm-5 | 121 | NOTES.md |

## H6: Models often break existing infrastructure (validation score degrades)

Compare generator buckets, not raw validation counts: `0-49`, `50-99`, `100-149`, and so on. Moving within the same 50-task bucket counts as `same`; `up` and `down` only count transitions between these generator buckets.

| model | episodes | validation_score_up | validation_score_same | validation_score_down |
| --- | --- | --- | --- | --- |
| gemini-2.5-flash | 7 | 28.6% | 42.9% | 28.6% |
| anthropic/claude-haiku-4-5@20251001 | 11 | 36.4% | 36.4% | 27.3% |
| gemma-4-31b | 22 | 50.0% | 22.7% | 27.3% |
| deepseek-ai/deepseek-v3.2 | 8 | 37.5% | 37.5% | 25.0% |
| zai/glm-5 | 12 | 50.0% | 25.0% | 25.0% |
| claude-opus-4-7 | 9 | 33.3% | 44.4% | 22.2% |
| gemini-3-flash-preview | 33 | 39.4% | 39.4% | 21.2% |
| gpt-5.4-2026-03-05 | 35 | 37.1% | 45.7% | 17.1% |
| anthropic/claude-opus-4-6@default | 8 | 87.5% | 12.5% | 0.0% |
| anthropic/claude-sonnet-4-6@default | 7 | 100.0% | 0.0% | 0.0% |
| gemini-3.1-flash-lite-preview | 5 | 0.0% | 100.0% | 0.0% |
| gemini-3.1-pro-preview | 5 | 100.0% | 0.0% | 0.0% |
| gpt-5.4-mini-2026-03-17 | 10 | 0.0% | 100.0% | 0.0% |

## H7: Models dont test created infrastructure

Among episodes that create or update `main.py`, count how often there is no later explicit execution of `main.py` in the same episode.

| model | episodes_with_main_py_update | episodes_main_py_updated_but_not_run | rate |
| --- | --- | --- | --- |
| gemma-4-31b | 19 | 18 | 94.7% |
| anthropic/claude-haiku-4-5@20251001 | 11 | 10 | 90.9% |
| deepseek-ai/deepseek-v3.2 | 8 | 7 | 87.5% |
| gpt-5.4-2026-03-05 | 31 | 27 | 87.1% |
| gemini-3-flash-preview | 24 | 18 | 75.0% |
| gemini-2.5-flash | 7 | 5 | 71.4% |
| gpt-5.4-mini-2026-03-17 | 8 | 5 | 62.5% |
| zai/glm-5 | 12 | 7 | 58.3% |
| anthropic/claude-opus-4-6@default | 7 | 3 | 42.9% |
| claude-opus-4-7 | 3 | 1 | 33.3% |
| gemini-3.1-pro-preview | 5 | 1 | 20.0% |
| anthropic/claude-sonnet-4-6@default | 7 | 1 | 14.3% |
| gemini-3.1-flash-lite-preview | 1 | 0 | 0.0% |

## H8: Models do not cleanup the mess in the infrastructure

Best-effort metric from logs: count files known from previous episodes that are never touched in the current episode, after also crediting local modules imported by the known `main.py` content as used.

| model | episodes_with_inherited_files | episodes_with_unused_inherited_files | avg_unused_inherited_files | common_unused_files |
| --- | --- | --- | --- | --- |
| anthropic/claude-opus-4-6@default | 7 | 100.0% | 11.29 | decode.py:7, encode.py:7, encode_msg.py:7, auth_sys2.py:5, decode_resp.py:5 |
| deepseek-ai/deepseek-v3.2 | 7 | 100.0% | 16.57 | encode_password.py:7, send_to_nested.py:7, delta_decoder.py:6, explore_encoding.py:6, test_encoding.py:6 |
| gemini-3.1-flash-lite-preview | 4 | 100.0% | 13.0 | decoder_try.py:4, decoder_v2.py:4, encoder_5bit.py:4, encoder_5bit_256.py:4, encoder_bytes.py:4 |
| gemini-3.1-pro-preview | 4 | 100.0% | 12.5 | auth.py:4, encode.py:4, test_decode.py:4, interact.py:3, main_new.py:3 |
| gemma-4-31b | 21 | 100.0% | 27.05 | decode_welcome.py:13, decoder.py:13, decoder_resp.py:13, encoder_activate.py:13, encoder_help.py:13 |
| zai/glm-5 | 11 | 100.0% | 68.0 | analyze_encoding.py:11, brute_2char.py:11, brute_3letter.py:11, brute_3lower.py:11, brute_3lower_fast.py:11 |
| gemini-3-flash-preview | 30 | 90.0% | 21.03 | decode_sys2.py:20, codec.py:15, decode_sys1.py:15, encode_sys1.py:15, decode.py:12 |
| claude-opus-4-7 | 8 | 87.5% | 0.88 | encode.py:7 |
| anthropic/claude-sonnet-4-6@default | 6 | 83.3% | 7.5 | /tmp/tmpp7z6j4b_/encode_decode.py:5, encode_decode.py:5, bitmixer_analyze.py:4, bitmixer_solve.py:4, bitmixer_solve2.py:4 |
| gemini-2.5-flash | 6 | 83.3% | 2.33 | encoding_utils.py:5, encode.py:3, delta_base32_encoder.py:3, codec.py:2, encoder.py:1 |
| anthropic/claude-haiku-4-5@20251001 | 10 | 70.0% | 0.7 | terminal_handler.py:7 |
| gpt-5.4-2026-03-05 | 32 | 53.1% | 0.69 | solver_tmp.py:13, bruteforce_auth.py:2, insert_bruteforce.py:2, short_bruteforce.py:2, state_probe.txt:2 |
| gpt-5.4-mini-2026-03-17 | 7 | 42.9% | 0.43 | main.py:2, notes.txt:1 |

## H9: Models do not decompose infrastructure into modules

Best-effort metric from the reconstructable `main.py` content: among episodes where `main.py` is known to exist, count how often it imports local non-stdlib modules that correspond to files in the workspace state.

| model | episodes_with_known_main_py | episodes_where_main_imports_local_modules | rate | local_modules_seen |
| --- | --- | --- | --- | --- |
| gemini-2.5-flash | 7 | 3 | 42.9% | encoding_utils.py:1, delta_base32_encoder.py:1, codec.py:1 |
| gemma-4-31b | 23 | 4 | 17.4% | codec.py:2, encode.py:1, utils.py:1 |
| zai/glm-5 | 12 | 1 | 8.3% | delta_base32.py:1 |
| anthropic/claude-haiku-4-5@20251001 | 11 | 0 | 0.0% | - |
| anthropic/claude-opus-4-6@default | 8 | 0 | 0.0% | - |
| anthropic/claude-sonnet-4-6@default | 7 | 0 | 0.0% | - |
| claude-opus-4-7 | 9 | 0 | 0.0% | - |
| deepseek-ai/deepseek-v3.2 | 8 | 0 | 0.0% | - |
| gemini-3-flash-preview | 33 | 0 | 0.0% | - |
| gemini-3.1-flash-lite-preview | 3 | 0 | 0.0% | - |
| gemini-3.1-pro-preview | 5 | 0 | 0.0% | - |
| gpt-5.4-2026-03-05 | 35 | 0 | 0.0% | - |
| gpt-5.4-mini-2026-03-17 | 10 | 0 | 0.0% | - |
