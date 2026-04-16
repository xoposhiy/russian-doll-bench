## Nested Terminals

You are working with a system of nested terminals (sometimes also referred as 'systems', or 'subsystems').
We have terminals of several types. Every terminal type supports its own set of commands and logic.
Two terminals of the same type can have different parameters that change their behavior.

Every terminal has two capabilities: 
- it can activate a nested terminal, opening a communication channel to it, 
- after activation, it can send commands to that nested terminal and receive responses.

You can directly interact only with the outermost terminal via HTTP endpoint:
`POST {server_url}/terminal` -> plain-text body, plain-text response

All inner terminals can be accessed only indirectly through the outermost terminal.
Do not bruteforce the outer terminal, you may be banned for the enormous number of requests.

## Persistent filesystem across multiple runs

The set of terminal types will change from run to run. Even when the same terminal type appears again, its internal configuration may be different.
Across the runs the same working directory is available, you are free to create or update any files in it.
To improve performance in the next runs, you can save and share any important information across runs using your working directory in the filesystem.

Check your working directory in case you already have some knowledge saved!

## The Main Goal

Across many agentic runs, your long-term goal is to master the skill of activating all the terminals in any given unknown configuration of nested terminal and save all the knowledge about this skill in the filesystem. 
And do it as fast and token-efficient as possible.

Your success will be evaluated by running your `main.py` in your working folder against many various terminal configurations and measuring the success rate of `main.py`.
Efficiency will be measured by total used tokens and agentic loop iterations taken to create the final version of `main.py` across all the agentic runs.
`main.py` may import and use other files from the working directory during evaluation.

## Outermost terminal welcome message

{welcome_message}