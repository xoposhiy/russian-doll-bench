# Tool Usage Report

## Tool calls

| model | tool_calls_total | give_up | read_file | run | update_file | write_file |
| --- | --- | --- | --- | --- | --- | --- |
| claude-opus-4-7 | 75 |  | 2.7% | 92.0% | 1.3% | 4.0% |
| gemini-3.1-pro-preview | 1202 | 0.2% |  | 80.4% | 4.8% | 14.5% |
| gpt-5 | 364 |  | 0.5% | 79.9% | 12.4% | 7.1% |
| gpt-5.4 | 111 |  |  | 96.4% |  | 3.6% |
| gpt-5.4-2026-03-05 | 194 |  |  | 96.9% |  | 3.1% |

## `run` subcommands

| model | run_subcommands_total | python | python3 | cat | curl | ls | sed | grep | tail | true | bash | cd | awk | * |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| claude-opus-4-7 | 82 | 3.7% | 25.6% | 14.6% | 8.5% | 18.3% | 14.6% |  |  |  |  | 9.8% |  | 4.9% |
| gemini-3.1-pro-preview | 973 | 22.1% | 30.9% | 27.2% | 13.7% | 1.2% | 1.0% | 1.5% | 0.5% | 0.1% |  |  | 0.4% | 1.2% |
| gpt-5 | 291 | 19.6% | 19.2% |  | 42.6% |  |  |  |  |  | 18.6% |  |  |  |
| gpt-5.4 | 107 | 79.4% | 14.0% | 0.9% | 5.6% |  |  |  |  |  |  |  |  |  |
| gpt-5.4-2026-03-05 | 190 | 96.3% |  | 1.6% |  | 0.5% |  | 0.5% | 0.5% | 0.5% |  |  |  |  |

## `agent_warning`

### claude-opus-4-7

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/75 | - |

### gemini-3.1-pro-preview

total: 12

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| model_call_failed: Model call failed: ServerError: 503 None. {'error': {'code': 503, 'message': 'Could not reach model, even after multiple retries. Try agai... | 4/1202 | 0.3% |
| model_call_failed: Model call failed: ServerError: 503 Service Unavailable. {'message': 'upstream connect error or disconnect/reset before headers. reset rea... | 2/1202 | 0.2% |
| model_call_failed: Model call failed: ServerError: 500 None. {'error': {'code': 500, 'message': 'An unexpected error occurred while communicating with the mo... | 1/1202 | 0.1% |
| model_call_failed: Model call failed: ServerError: 503 Service Unavailable. {'message': 'upstream connect error or disconnect/reset before headers. reset rea... | 1/1202 | 0.1% |
| model_call_failed: Model call failed: ClientError: 403 None. {'error': {'code': 403, 'message': 'The estimated cost of this operation ($0.82582) exceeds your... | 1/1202 | 0.1% |
| model_call_failed: Model call failed: ClientError: 403 None. {'error': {'code': 403, 'message': 'The estimated cost of this operation ($0.789354) exceeds you... | 1/1202 | 0.1% |
| model_call_failed: Model call failed: ClientError: 403 None. {'error': {'code': 403, 'message': 'The estimated cost of this operation ($0.787212) exceeds you... | 1/1202 | 0.1% |
| model_call_failed: Model call failed: ClientError: 403 None. {'error': {'code': 403, 'message': 'The estimated cost of this operation ($0.786466) exceeds you... | 1/1202 | 0.1% |

### gpt-5

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/364 | - |

### gpt-5.4

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/111 | - |

### gpt-5.4-2026-03-05

total: 8

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| unexpected_tool_args: run: ['timeout'] | 8/194 | 4.1% |

