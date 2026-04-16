# Russian Doll 🪆: Measuring Adaptive Infrastructure Building Across Agentic Episodes

## Problem Statement

Models are good at single programming tasks, but they still struggle to build infrastructure that helps in future sessions. The ability to develop their own harness matters increasingly as models are deployed in long-horizon agentic settings. Russian Doll is designed to make this gap directly observable and quantifiable.

The benchmark targets **executive functions** specifically:

- *planning* — building abstractions that pay off across future episodes;
- *cognitive flexibility* — exploratory behavior; adapting existing code to counterexamples; switching between solving the immediate task and building long-running infrastructure;
- *working memory* — coordinating during exploratory behavior: hypothesis formation and tracking across a multi-step interaction.

## Task & Benchmark Construction

### Benchmark Structure

The benchmark runs a **curriculum of 10 task families** in order of increasing difficulty. Each family comprises 50 tasks. Tasks within a family share the same underlying structure but differ in configuration — the agent must produce a solution that generalizes across all instances, not just the one.

The agent's goal across multiple runs is to develop a `main.py` that solves any task without LLM intervention.
The working directory persists across episodes and stores any infrastructure the agent creates: `main.py`, other modules, scripts, and notes the agent leaves for itself.

Benchmark Algorithm:

1. Run the agent's `main.py` on all tasks and find the first that fails, in curriculum order.
2. If none fail: success, stop.
3. If the failing task's family had already failed 5 times: failure to generalize, stop.
4. Otherwise, give the agent that failing task to solve interactively and update its infrastructure; after — go to 1.

Important: validation of the `main.py` never invokes the model. The score reflects whether the agent's *code* generalizes across held-out instances.

This is a form of **adaptive learning**: the pace of curriculum progression depends on the success of generalization in previous episodes.
This lets us measure not only how far the model can advance, but also how fast.

### 🪆 Nesting as an Infrastructure Incentive 

Infrastructure pays off on complex tasks. We construct complex tasks by nesting subtasks: solving one unlocks the next. This rewards reusable infrastructure when subtask types recur. 
Complexity scales with adding nesting levels, subtask types, and longer chains.

In this benchmark, each task is a chain of nested components — terminals.

#### Terminal — The Building Block

A **terminal** is a text interface: the agent sends a command, the terminal replies. Each terminal type has its own command set and rules that the agent must discover through exploration. 
Terminals are nested: each terminal can relay commands to the inner one. However, to reach the inner terminal, the agent must first **activate** the outer one by decoding its interface and solving a small coding puzzle. 
Every chain ends with a trivial **final terminal** that completes the task when it receives a command `ACTIVATE TERMINAL` without any coding puzzle.

Expected agent behavior:

1. Explore the existing infrastructure (`main.py` and other contents of the working directory), use it, and analyze its errors.
2. Discover the command set and mechanics of the unknown terminal by probing and analyzing error messages.
3. Write and debug a script to activate the terminal.
4. Discover in the same manner how to relay commands to the nested terminal, then continue from step 1 for that terminal.
5. Once the full chain is activated, update infrastructure to handle these terminal types generically.

Whether this yields a reusable generalization or just another local patch is revealed in the next benchmark cycle.

[Example of a terminal solution trace](https://github.com/xoposhiy/russian-doll-bench/blob/main/server/terminals/sys32/solution-trace.txt)

### Evaluation

**Primary metric: task families solved**. A family is solved when `main.py` passes all 50 of its tasks.

**Secondary metrics: efficiency**. Total number of agentic loop iterations spent *up to the best primary metric achieved*.

They are combined in a single score:

```
inefficiency_penalty = min(99, total_iterations_spent / fully_passed_generators)
score = 100 * fully_passed_generators - inefficiency_penalty
```

These metrics separate three qualitatively distinct behaviors:

- **Strong:** After a single example, generalize the solution into `main.py`, able to pass all remaining tasks in that family. Infrastructure is reusable even for deeply nested chains.
- **Medium:** Code improves with each counterexample but needs several exposures. May get stuck or temporarily degrade on later families.
- **Weak:** Solves the presented task but fails to generalize, burns the retry budget, and stalls on early families.

---

## Dataset

Tasks are procedurally generated from fixed seeds. Solution correctness is objective — the chain is either fully activated or not — and is automatically verified. 
Each terminal type is solvable standalone by current frontier models, confirming puzzle correctness and solvability.

### Terminal Types

Each terminal's solvability and difficulty were tested with the `gemini-3-flash-preview` model.
Difficulty is the average number of agentic-loop iterations required to solve the terminal (3 runs per terminal):

| Terminal | Difficulty | Puzzle |
|---|---|---|
| **Sys32** | 20.3 | Custom base32-like encoding. |
| **Cipher** | 24.6 | Substitution cipher defined by formula. |
| **BitMixer** | 43.3 | Reverse-engineer a bit-permutation from examples. |
| **Hash** | 54.3 | Reverse-engineer a polynomial hash function from examples. |
| **Maze** | 83.7 | Shortest-path problem on a weighted grid and XOR encryption. |

[Full table data](https://github.com/xoposhiy/russian-doll-bench/blob/main/reports/terminals-difficulty.csv)

[Terminal implementations](https://github.com/xoposhiy/russian-doll-bench/tree/main/server/terminals)

### Task Families

Difficulty rises by increasing nesting depth, introducing new terminal types, and moving unknown types deeper into the chain.

`A - B` means outer terminal A wrapping inner terminal B.

| # | Family spec | Max score if solved up to here |
|---|---|---|
| 1 | `Sys32` | 100 |
| 2 | `Sys32 - Sys32` | 200 |
| 3 | `Sys32 - Sys32 - Sys32` | 300 |
| 4 | `BitMixer - Sys32 - Sys32` | 400 |
| 5 | `T - T - T`, where `T ∈ {Sys32, BitMixer}` | 500 |
| 6 | `T - T - T - T`, where `T ∈ {Sys32, BitMixer}` | 600 |
| 7 | `T - Cipher - T - T`, where `T ∈ {Sys32, BitMixer}` | 700 |
| 8 | `T - T - Hash - T`, where `T ∈ {Sys32, BitMixer, Cipher}` | 800 |
| 9 | `T - T - T - Maze`, where `T ∈ {Sys32, BitMixer, Cipher, Hash}` | 900 |
| 10 | Nesting depth 1–4, all 5 terminal types | 1000 |

---

## Technical Details

The agent runs a simple tool-calling loop (100-iteration cap) with five tools: read, write, and update files; run shell commands; and give up.
The system prompt describes only the environment and the high-level goal. We tried to avoid explicit instructions, but two exceptions were necessary:

1. We explicitly ask models to check the working directory before solving. Without this, even the strongest models ignore existing solutions.
2. We remind the model to update `main.py` after solving the task. Without this, models more often forget to update `main.py`.

[Specific Prompts](https://github.com/xoposhiy/russian-doll-bench/tree/main/benchmark/prompts)

---

## Results, Insights, and Conclusions

Surprisingly, the three strongest models — Gemini-3.1-Pro, Claude-Opus-4.6, Claude-Sonnet-4.6 — were able to solve all task families. The benchmark clearly separates strong and weak models, with GPT-5.4 falling in the middle.

**Failure modes:**
- Without explicit instruction, most models do not explore their working directory before solving, even when informed that they operate across multiple sessions with a shared directory. Weak models sometimes ignore it, even with explicit instruction.
- Models often break existing infrastructure, decreasing their validation score. They very rarely test their final changes to `main.py`, which is a likely cause of this degradation.
- Weak models struggle with generalization of their ad-hoc solutions into `main.py`.

**Additional qualitative signals:**
Our log analysis surfaced several signals of weak infrastructure-building ability that are not captured by the benchmark score. Future work could design benchmark variants that measure these signals more directly.

- Some models (Claude, GPT-5.4, GLM) carefully accumulate knowledge in text files and comments in the code, while others (the Gemini family) almost never do. Unfortunately, our tasks did not penalize lost knowledge across sessions strongly enough.
- Models almost never clean up their working directory, often leaving 10+ unused one-off scripts. However, with a single entry point in `main.py`, this did not cause major downstream problems — models just ignore junk files.
- Models almost never decompose their infrastructure into modules despite the modular structure of the tasks. However, with the final `main.py` staying below 40k characters, this probably did not create major difficulties.

[Detailed hypothesis analysis](https://github.com/xoposhiy/russian-doll-bench/blob/main/reports/hypotheses_report.md) and [tool-call analysis](https://github.com/xoposhiy/russian-doll-bench/blob/main/reports/tool_usage_report.md)

## GPT-5.4 reruns

We expected GPT-5.4 to be in the league of strong models. We therefore reran gpt-5.4 five times, and the maximum observed score was 680.29, which clearly separates it from the strong models.
Compared with the strongest models, it consistently showed weaker exploratory behavior, occasional infrastructure degradation, and more incorrect tool calls.

