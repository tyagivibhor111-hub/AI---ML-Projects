"""
MCP server that hands out tools for controlling live Jupyter kernels.

Run with: python server.py
Debug the protocol with: npx @modelcontextprotocol/inspector python server.py

Note: kernels are kept in a dict keyed by a name the caller chooses, not by
some internal id - makes it way easier for the model (and for us, testing
by hand) to say "run this in the 'scratch' kernel" instead of juggling ids.
"""

import base64
import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from kernel_manager import ManagedKernel

mcp = FastMCP("jupyter-bridge")

# not thread-safe, not trying to be - MCP stdio servers are single-client
# and effectively single-threaded for our purposes here
_kernels: dict[str, ManagedKernel] = {}


def _get_or_create(session: str) -> ManagedKernel:
    if session not in _kernels:
        _kernels[session] = ManagedKernel()
    return _kernels[session]


@mcp.tool()
def start_kernel(session: str = "default") -> str:
    """Start a new named Jupyter kernel, or report the existing one's connection file."""
    kernel = _get_or_create(session)
    return (
        f"kernel '{session}' ready. connection file: {kernel.connection_file}\n"
        f"(open this same kernel in JupyterLab via Kernel > Change Kernel, "
        f"or 'jupyter console --existing {kernel.connection_file}')"
    )


@mcp.tool()
def execute_code(code: str, session: str = "default", timeout: float = 30.0) -> list:
    """
    Run code in the given kernel session and return its output.
    Persists across calls - variables defined here are visible next time.
    """
    kernel = _get_or_create(session)
    result = kernel.execute(code, timeout=timeout)

    blocks = []

    if result.timed_out:
        blocks.append(TextContent(
            type="text",
            text=f"[timed out after {timeout}s - kernel was interrupted, "
                 f"any partial state before the hang should still be there]"
        ))

    if result.stdout:
        blocks.append(TextContent(type="text", text=result.stdout))
    if result.result_text:
        blocks.append(TextContent(type="text", text=f"Out: {result.result_text}"))
    if result.stderr:
        blocks.append(TextContent(type="text", text=f"stderr: {result.stderr}"))
    if result.error_traceback:
        blocks.append(TextContent(type="text", text=result.error_traceback))

    for img_b64 in result.images_png_b64:
        blocks.append(ImageContent(type="image", data=img_b64, mimeType="image/png"))

    if not blocks:
        blocks.append(TextContent(type="text", text="(no output)"))

    return blocks


@mcp.tool()
def list_variables(session: str = "default") -> str:
    """List variables currently defined in the kernel's namespace, with type and a short repr."""
    kernel = _get_or_create(session)
    raw = kernel.introspect_variables()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw or "(couldn't introspect - kernel may be busy)"
    lines = [f"{k}: {v['type']} = {v['repr']}" for k, v in parsed.items()]
    return "\n".join(lines) if lines else "(no user-defined variables yet)"


@mcp.tool()
def restart_kernel(session: str = "default") -> str:
    """Wipe the kernel's state and start fresh. Use when things get into a weird state."""
    if session in _kernels:
        _kernels[session].restart()
        return f"kernel '{session}' restarted, namespace cleared"
    return f"no kernel named '{session}' running yet"


@mcp.tool()
def interrupt_kernel(session: str = "default") -> str:
    """Send a KeyboardInterrupt to a kernel that's stuck (e.g. accidental infinite loop)."""
    if session in _kernels:
        _kernels[session].interrupt()
        return f"interrupt sent to '{session}'"
    return f"no kernel named '{session}' running yet"


@mcp.tool()
def shutdown_kernel(session: str = "default") -> str:
    """Cleanly shut down and forget a kernel session."""
    if session in _kernels:
        _kernels[session].shutdown()
        del _kernels[session]
        return f"kernel '{session}' shut down"
    return f"no kernel named '{session}' to shut down"


@mcp.tool()
def list_sessions() -> str:
    """List currently running kernel session names."""
    return ", ".join(_kernels.keys()) if _kernels else "(none running)"


if __name__ == "__main__":
    # stdio transport - this is what Claude Desktop/Code expect for local servers
    mcp.run(transport="stdio")
