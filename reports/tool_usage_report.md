# Tool Usage Report

## Tool calls

| model | tool_calls_total | give_up | read_file | run | update_file | write_file |
| --- | --- | --- | --- | --- | --- | --- |
| anthropic/claude-haiku-4-5@20251001 | 208 |  | 9.6% | 76.0% | 0.5% | 13.9% |
| anthropic/claude-opus-4-6@default | 177 |  | 2.8% | 70.1% | 3.4% | 23.7% |
| anthropic/claude-sonnet-4-6@default | 203 |  | 7.4% | 76.4% | 1.5% | 14.8% |
| claude-opus-4-7 | 81 |  | 3.7% | 79.0% | 11.1% | 6.2% |
| deepseek-ai/deepseek-v3.2 | 188 |  | 14.9% | 56.4% | 6.4% | 22.3% |
| gemini-2.5-flash | 147 |  | 2.7% | 78.9% | 6.8% | 11.6% |
| gemini-3-flash-preview | 1044 |  | 1.1% | 72.1% | 10.7% | 16.0% |
| gemini-3.1-flash-lite-preview | 203 | 2.5% |  | 97.0% |  | 0.5% |
| gemini-3.1-pro-preview | 95 |  |  | 86.3% |  | 13.7% |
| gemma-4-31b | 800 |  | 1.1% | 71.6% | 8.0% | 19.2% |
| gpt-5.4-2026-03-05 | 754 | 1.2% | 8.6% | 79.2% | 3.2% | 7.8% |
| gpt-5.4-mini-2026-03-17 | 229 | 3.1% | 2.6% | 86.9% |  | 7.4% |
| zai/glm-5 | 524 |  | 5.0% | 57.6% | 5.3% | 32.1% |

## `run` subcommands

| model | run_subcommands_total | python3 | curl | ls | cat | python | pwd | echo | for | do | cd | find | sed | * |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| anthropic/claude-haiku-4-5@20251001 | 188 | 38.3% | 2.7% | 5.9% | 34.0% | 1.1% | 4.8% |  |  |  | 12.8% |  |  | 0.5% |
| anthropic/claude-opus-4-6@default | 137 | 16.1% | 19.7% | 6.6% | 24.8% | 20.4% | 2.9% | 4.4% | 0.7% |  | 2.9% |  |  | 1.5% |
| anthropic/claude-sonnet-4-6@default | 239 | 22.6% | 13.0% | 8.8% | 6.7% | 11.3% | 0.8% | 2.1% | 0.8% | 0.4% | 26.4% | 3.3% |  | 3.8% |
| claude-opus-4-7 | 72 | 26.4% | 26.4% | 13.9% | 15.3% |  | 1.4% | 1.4% | 1.4% | 1.4% | 4.2% |  | 6.9% | 1.4% |
| deepseek-ai/deepseek-v3.2 | 106 | 53.8% | 27.4% | 7.5% |  | 11.3% |  |  |  |  |  |  |  |  |
| gemini-2.5-flash | 116 | 40.5% | 41.4% | 1.7% | 1.7% | 12.9% |  |  |  |  |  |  |  | 1.7% |
| gemini-3-flash-preview | 800 | 56.6% | 36.5% | 3.2% | 2.8% |  |  |  |  |  |  |  |  | 0.9% |
| gemini-3.1-flash-lite-preview | 187 | 9.1% | 45.5% | 2.7% | 41.7% |  |  |  |  |  |  |  |  | 1.1% |
| gemini-3.1-pro-preview | 82 | 47.6% | 3.7% | 6.1% | 39.0% |  |  |  |  |  |  |  |  | 3.7% |
| gemma-4-31b | 645 | 54.1% | 34.6% | 0.5% | 0.6% |  |  |  | 0.2% | 0.2% |  |  | 0.5% | 9.5% |
| gpt-5.4-2026-03-05 | 702 | 37.7% | 7.5% | 5.0% | 2.3% | 34.3% | 5.0% | 0.3% | 0.4% | 0.4% |  | 5.0% |  | 2.0% |
| gpt-5.4-mini-2026-03-17 | 221 | 73.8% | 2.3% | 2.7% | 0.9% | 10.9% | 2.7% | 2.3% | 0.5% | 0.5% |  | 1.8% | 0.9% | 0.9% |
| zai/glm-5 | 316 | 61.1% | 28.5% | 4.4% | 0.3% |  | 0.9% | 1.6% |  | 0.3% | 1.3% |  |  | 1.6% |

## `agent_warning`

### anthropic/claude-haiku-4-5@20251001

total: 1

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| unexpected_tool_args: update_file: ['str_to_replace_with'] | 1/208 | 0.5% |

### anthropic/claude-opus-4-6@default

total: 3

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| no_response | 2/177 | 1.1% |
| no_tool_call | 1/177 | 0.6% |

### anthropic/claude-sonnet-4-6@default

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/203 | - |

### claude-opus-4-7

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/81 | - |

### deepseek-ai/deepseek-v3.2

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/188 | - |

### gemini-2.5-flash

total: 3

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| no_function_call | 1/147 | 0.7% |
| model_call_failed: Model call failed: ClientError: 400 None. {'error': {'code': 400, 'message': 'Unable to submit request because it must include at least on... | 1/147 | 0.7% |
| unexpected_tool_args: update_file: ['content'] | 1/147 | 0.7% |

### gemini-3-flash-preview

total: 12

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| unexpected_tool_args: update_file: ['content'] | 8/1044 | 0.8% |
| model_call_failed: Model call failed: ServerError: 500 None. {'error': {'code': 500, 'message': 'An unexpected error occurred while communicating with the mo... | 3/1044 | 0.3% |
| no_function_call: call:default_api:run{command:python3 decode_sys3_welcome.py | 1/1044 | 0.1% |

### gemini-3.1-flash-lite-preview

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/203 | - |

### gemini-3.1-pro-preview

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/95 | - |

### gemma-4-31b

total: 6

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| no_function_call | 3/800 | 0.4% |
| unexpected_tool_args: update_file: ['content'] | 1/800 | 0.1% |
| model_call_failed: Model call failed: ServerError: 503 Service Unavailable. {'message': 'upstream connect error or disconnect/reset before headers. reset rea... | 1/800 | 0.1% |
| model_call_failed: Model call failed: ClientError: 400 None. {'error': {'code': 400, 'message': 'Unsupported input part type: go/debugproto   \nthought: true... | 1/800 | 0.1% |

### gpt-5.4-2026-03-05

total: 30

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| no_tool_call | 15/754 | 2.0% |
| no_response | 9/754 | 1.2% |
| unexpected_tool_args: run: ['timeout'] | 5/754 | 0.7% |
| unexpected_tool_args: write_file: ['operation'] | 1/754 | 0.1% |

### gpt-5.4-mini-2026-03-17

total: 31

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| no_response | 19/229 | 8.3% |
| no_tool_call | 7/229 | 3.1% |
| unexpected_tool_args: run: ['timeout'] | 5/229 | 2.2% |

### zai/glm-5

total: 0

| warning | count | pct_of_tool_calls |
| --- | --- | --- |
| - | 0/524 | - |

