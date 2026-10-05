# 🤖 AutoFix-Agents: A Multi-Agent, Self-Correcting Bug-Fixing System

An **agentic AI** project where three cooperating agents (Planner, Executor, Critic) autonomously
diagnose and fix bugs in Python code, using real tool calls, episodic memory, reflection, and a
**hidden-test evaluation harness** that catches agents which only "game" the visible tests.

Everything lives in one notebook: `agentic_autofix.ipynb`.


## Architecture

```
                 ┌────────────┐   plan + memory hints
 bug report ───▶ │  PLANNER   │────────────────────────┐
                 └────────────┘                        ▼
        ┌───────────────────────────────────────────────────────┐
        │ EXECUTOR (ReAct loop with tool use)                   │
        │  list_files · read_file · write_file · run_tests      │
        │  search_memory · finish                               │
        └───────────────┬───────────────────────────────────────┘
                        │ submission
                        ▼
                 ┌────────────┐  fail   ┌────────────┐
                 │   CRITIC   │────────▶│ REFLECTOR  │──▶ feedback ─▶ back to EXECUTOR
                 │ visible +  │         └────────────┘
                 │ hidden tests│ pass
                 └─────┬──────┘
                       ▼
              store lesson in MEMORY
```

## Project structure

```
agentic_autofix.ipynb   # the full project (code + comments)
README.md               # this file
```

## Setup

```bash
pip install jupyter anthropic      # anthropic only needed for LIVE mode
export ANTHROPIC_API_KEY=sk-ant-...   # optional
jupyter notebook agentic_autofix.ipynb
```

Python 3.9+ is required. No other dependencies.

## Modes

- **LIVE**: used automatically when `ANTHROPIC_API_KEY` is set. Real Claude agents solve the tasks.
- **DEMO**: used otherwise. A scripted stand-in replays agent behaviour so you can verify the whole
  pipeline (tools, critic, reflection loop, metrics) offline and for free. DEMO results are **not**
  a measure of model capability.

Override with `FORCE_DEMO = True` or the `AGENT_MODEL` environment variable.

## Benchmark tasks

| ID | Bug | Subtlety |
|---|---|---|
| `binary_search` | Loop bound off by one | Fails only on boundary/single-element inputs |
| `mutable_default` | Shared mutable default argument | State leaks between calls |
| `lru_cache` | Reads don't update recency | Wrong eviction order |
| `merge_intervals` | Merged end overwritten, not maxed | Nested intervals |
| `token_bucket` | Two bugs (`>` vs `>=`, uncapped refill) | Visible tests catch only one; hidden tests catch the other |

## Reading the results

The final table reports, per task: `solved` (passes visible **and** hidden tests), `rounds`
(Critic rejections + 1), LLM `steps`, `tools` calls, token usage, and wall-clock seconds.
`token_bucket` is designed to trigger the Critic → Reflector → retry path.

## Key design decisions

- **Hidden tests as ground truth.** Visible tests pass is not the same as correct. The Critic's
  verdict is independent of the Executor's own `run_tests` calls.
- **Feedback is the failure report, not the hidden test source.** The Executor sees tracebacks, not the tests.
- **Provider-agnostic LLM interface.** `LLM.chat(system, messages, tools)` returns normalized blocks,
  so another provider is a ~20 line adapter.

## Limitations

- The sandbox is a subprocess with timeouts, **not** a container. Do not run untrusted code with it.
- The benchmark is small (5 tasks) and single-file; it is a framework demo, not a SWE-bench result.
- TF-IDF memory is lexical; embeddings would retrieve better on paraphrased bugs.

## Roadmap / extensions

1. Docker or `nsjail` sandbox for real isolation.
2. Multi-file repos and a `grep`/`run_command` tool; try SWE-bench-Lite instances.
3. Parallel Executors with self-consistency voting, Critic picks the best patch.
4. Embedding-based memory and a learned router that picks cheap vs strong models per step.
5. Ablations: memory on/off, reflection on/off, planner on/off (see the ablation cell).

## Resume bullet (fill in your own measured numbers)

> Built a Planner/Executor/Critic multi-agent system with tool use, episodic memory, and
> reflection; evaluated with hidden-test harness to detect test-overfitting, achieving **X/Y**
> solve rate across **N** tasks with **Z** average tool calls.
