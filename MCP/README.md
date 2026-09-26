# MCP Jupyter Bridge

**A Model Context Protocol server that gives an LLM a real, persistent Jupyter kernel to work with — not a sandboxed code-exec toy, but the same kernel you're looking at in JupyterLab.**

This is on the harder end of things to build well because it isn't really one project, it's three glued together: the MCP protocol itself (async, typed tool schemas, resources vs tools), Jupyter's kernel/messaging protocol (ZMQ sockets, iopub vs shell channels, message ordering), and the annoying-but-real problem of turning rich cell output (stdout, images, tracebacks, widgets) into something an LLM can actually read.

## Why this is worth putting on a portfolio

Most "AI agent runs code" demos spin up a throwaway sandbox and kill it after one snippet. That's fine for a leetcode-style code executor, but it's not how a data scientist actually works — state persists, you build up a `df` over 20 cells, you plot something, you look at the plot, you go back and fix cell 7. This project makes the AI a participant in *that* workflow: it attaches to a live kernel, keeps it alive across many tool calls, and can hand you back a matplotlib figure as an image the model can actually reason about.

Reviewers who've touched Jupyter internals or written an MCP server will recognize this is not a wrapper around `exec()`.

## Architecture

```
                 stdio / MCP protocol
Claude / MCP  <───────────────────────►  server.py  (FastMCP tools)
client                                       │
                                              │ owns
                                              ▼
                                     kernel_manager.py
                                              │
                                   jupyter_client (ZMQ)
                                              │
                                              ▼
                                   IPython Kernel process
                                   (same one JupyterLab
                                    would connect to)
```

Key design decision: the kernel is started with `KernelManager.write_connection_file()`, so you can open **JupyterLab separately, point it at the same connection file, and watch the AI's variables/plots update live in your notebook.** That's the "hard" part that makes it feel real instead of a demo.

## Milestones (build in this order)

1. **Kernel lifecycle** — start/stop/restart a kernel, confirm you can see it in `jupyter kernelspec list` / `jupyter --runtime-dir`.
2. **Single execute_code tool** — send code, block until idle, return stdout/stderr. Get comfortable with iopub message types (`stream`, `execute_result`, `error`, `display_data`).
3. **Rich output** — capture `image/png` from `display_data` (e.g. `plt.show()`), base64-encode, return as an MCP image content block instead of just text.
4. **State inspection** — `list_variables` / `inspect_variable` tools that run a small introspection snippet under the hood and parse the result instead of just re-running arbitrary user code.
5. **Timeouts + interrupts** — a cell that hangs (infinite loop, `input()` call) shouldn't take down your MCP server. Add a hard timeout + kernel interrupt.
6. **Multi-session** — support more than one named kernel at once (e.g. `"analysis"` and `"scratch"`), so the model can keep an experiment kernel separate from a clean one.
7. **(Stretch) Checkpointing** — periodically `%who`/pickle key variables so a crashed kernel can be partially recovered.

## Dev workflow (VS Code + JupyterLab side by side)

- Write/debug `server.py` and `kernel_manager.py` in **VS Code**. Use the included `.vscode/launch.json`-style config (add one) to run the server directly with the debugger attached rather than through an MCP client, so you can breakpoint the ZMQ message loop.
- Test the actual protocol handshake with the **MCP Inspector** (`npx @modelcontextprotocol/inspector python server.py`) before wiring it into Claude Desktop/Code.
- Run **JupyterLab** (`jupyter lab`) pointed at the same runtime dir so you can visually confirm the kernel state the AI is manipulating. This is the part that makes the demo/video convincing — show a plot appear in your notebook because the AI called `execute_code`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py   # runs the MCP server over stdio
```

## Files

- `kernel_manager.py` — thin-ish wrapper around `jupyter_client`, handles the ZMQ message pump and output capture.
- `server.py` — the actual MCP server, tool definitions live here.
- `requirements.txt`

## Resume bullet (once it works)

> Built an MCP server bridging LLM tool-calling to a live Jupyter kernel via ZMQ, supporting persistent multi-turn code execution, rich output capture (plots/images), and interrupt-safe timeouts — enabling AI-driven, notebook-visible data analysis workflows.