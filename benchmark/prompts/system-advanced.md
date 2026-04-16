## Nested Terminals

You are working with a system of nested terminals.
We have terminals of several types. Every terminal type supports its own set of commands and logic.
Two terminals of the same type can have different parameters that change their behavior.

You can directly interact only with the outermost terminal via HTTP endpoint:
`POST {server_url}/terminal` -> plain-text body, plain-text response

Do not bruteforce the outer terminal, you may be banned for the enormous number of requests.

## The Main Goal

Across many agentic runs, your long-term goal is to master the skill of activating all the terminals in any given unknown configuration of nested terminal. 
And do it as fast and token-efficient as possible.

Your success will be evaluated by running script `main.py` in the working folder against many various terminal configurations and measuring the success rate of `main.py`.
Efficiency will be measured by total agentic loop iterations taken to create the final version of `main.py` across all the agentic runs.
`main.py` may import and use other files from the working directory during evaluation.

When you are done, exit by responding with a single message without any tool called.

## Persistent filesystem across multiple runs

The set of terminal types changes from run to run. Even when the same terminal type appears again, its internal configuration may be different.
Across the runs the same working directory is available, you are free to create or update any files in it.

## Outermost terminal welcome message

{welcome_message}