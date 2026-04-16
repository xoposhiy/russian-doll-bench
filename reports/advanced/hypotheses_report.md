# Log Hypotheses Report

Source: top-level `*.jsonl` files directly in `logs/advanced`.

## H1: Creating infrastructure is harder than just solving the task

Among episodes where the current training chain is solved (`run_end.done=true`), count how often validation still does not reach the next 50-task generator boundary. Example: if validation was 50/500 before the run, success means reaching at least 100/500 after the run.

| model | episodes_solved_chain | episodes_solved_chain_but_validation_failed | rate |
| --- | --- | --- | --- |
| gpt-5.4-2026-03-05 | 2 | 2 | 100.0% |
| claude-opus-4-7 | 14 | 9 | 64.3% |
| gpt-5 | 11 | 6 | 54.5% |
| gpt-5.4 | 2 | 1 | 50.0% |
| gemini-3.1-pro-preview | 22 | 6 | 27.3% |

## H2: Models ignore existing infrastructure, focusing on resolving a task from scratch

Among episodes that start after `main.py` already exists from an earlier episode, count how often the model never reads or explicitly references `main.py`.

| model | episodes_with_preexisting_main_py | episodes_without_main_py_read | rate |
| --- | --- | --- | --- |
| gpt-5.4 | 4 | 3 | 75.0% |
| gpt-5.4-2026-03-05 | 8 | 6 | 75.0% |
| gemini-3.1-pro-preview | 26 | 8 | 30.8% |
| claude-opus-4-7 | 13 | 0 | 0.0% |
| gpt-5 | 10 | 0 | 0.0% |

## H3: Models do not explore the working directory early

Count episodes with no `ls` subcommand inside the first 3 agent iterations. `run` commands split on `&&`, `;`, and `||`.

| model | episodes_total | episodes_without_ls_in_first_3_iterations | rate |
| --- | --- | --- | --- |
| gemini-3.1-pro-preview | 28 | 28 | 100.0% |
| gpt-5 | 11 | 11 | 100.0% |
| gpt-5.4 | 6 | 6 | 100.0% |
| gpt-5.4-2026-03-05 | 10 | 10 | 100.0% |
| claude-opus-4-7 | 14 | 0 | 0.0% |

## H4: Models forget to update main.py

Among episodes where all terminals were activated (`run_summary.activated_terminals_count == run_summary.total_terminals`), count how often `main.py` is neither created nor updated during the episode. Episodes that failed to activate the full terminal set are excluded.

| model | episodes_with_all_terminals_activated | episodes_without_main_py_update | rate |
| --- | --- | --- | --- |
| gpt-5.4-2026-03-05 | 2 | 2 | 100.0% |
| claude-opus-4-7 | 14 | 12 | 85.7% |
| gpt-5.4 | 2 | 1 | 50.0% |
| gemini-3.1-pro-preview | 22 | 1 | 4.5% |
| gpt-5 | 11 | 0 | 0.0% |

## H5: Models almost never create non-Python files

List every created file that is not `*.py`.

| model | created_files_total | non_python_files_list |
| --- | --- | --- |
| claude-opus-4-7 | 2 | - |
| gemini-3.1-pro-preview | 77 | hash_init_fix.txt |
| gpt-5 | 12 | README_strategy.md |
| gpt-5.4 | 2 | - |
| gpt-5.4-2026-03-05 | 2 | - |

## H6: Models often break existing infrastructure (validation score degrades)

Compare generator buckets, not raw validation counts: `0-49`, `50-99`, `100-149`, and so on. Moving within the same 50-task bucket counts as `same`; `up` and `down` only count transitions between these generator buckets.

| model | episodes | validation_score_up | validation_score_same | validation_score_down |
| --- | --- | --- | --- | --- |
| gpt-5 | 11 | 45.5% | 18.2% | 36.4% |
| claude-opus-4-7 | 14 | 35.7% | 35.7% | 28.6% |
| gemini-3.1-pro-preview | 28 | 57.1% | 21.4% | 21.4% |
| gpt-5.4 | 6 | 16.7% | 83.3% | 0.0% |
| gpt-5.4-2026-03-05 | 10 | 0.0% | 100.0% | 0.0% |

## H7: Models dont test created infrastructure

Among episodes that create or update `main.py`, count how often there is no later explicit execution of `main.py` in the same episode.

| model | episodes_with_main_py_update | episodes_main_py_updated_but_not_run | rate |
| --- | --- | --- | --- |
| gpt-5.4-2026-03-05 | 8 | 6 | 75.0% |
| gpt-5.4 | 5 | 3 | 60.0% |
| gemini-3.1-pro-preview | 22 | 2 | 9.1% |
| gpt-5 | 11 | 1 | 9.1% |
| claude-opus-4-7 | 2 | 0 | 0.0% |

## H8: Models do not cleanup the mess in the infrastructure

Best-effort metric from logs: count files known from previous episodes that are never touched in the current episode, after also crediting local modules imported by the known `main.py` content as used.

| model | episodes_with_inherited_files | episodes_with_unused_inherited_files | avg_unused_inherited_files | common_unused_files |
| --- | --- | --- | --- | --- |
| gemini-3.1-pro-preview | 26 | 100.0% | 55.73 | mapper.py:24, test_encode.py:23, test_decode.py:20, test3.py:18, test4.py:18 |
| gpt-5 | 10 | 100.0% | 6.5 | README_strategy.md:10, decode_text.py:9, encode_text.py:9, guess_password.py:9, hack.py:9 |
| gpt-5.4 | 4 | 25.0% | 0.25 | main.py:1 |
| gpt-5.4-2026-03-05 | 8 | 25.0% | 0.25 | main.py:2 |
| claude-opus-4-7 | 13 | 0.0% | 0.0 | - |

## H9: Models do not decompose infrastructure into modules

Best-effort metric from the reconstructable `main.py` content: among episodes where `main.py` is known to exist, count how often it imports local non-stdlib modules that correspond to files in the workspace state.

| model | episodes_with_known_main_py | episodes_where_main_imports_local_modules | rate | local_modules_seen |
| --- | --- | --- | --- | --- |
| gpt-5 | 11 | 2 | 18.2% | encoder.py:1, codec.py:1 |
| claude-opus-4-7 | 14 | 0 | 0.0% | - |
| gemini-3.1-pro-preview | 28 | 0 | 0.0% | - |
| gpt-5.4 | 6 | 0 | 0.0% | - |
| gpt-5.4-2026-03-05 | 10 | 0 | 0.0% | - |
