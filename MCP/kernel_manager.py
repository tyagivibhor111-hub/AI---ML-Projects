"""
Wraps jupyter_client so server.py doesn't have to know about ZMQ message types.

Heads up for future me: the iopub channel is where basically everything
interesting shows up (stdout, plots, errors) but messages can arrive in a
slightly annoying order — 'busy' -> actual output -> 'idle'. We just drain
the queue until we see idle and bucket everything by msg_type.
"""

import base64
import queue
import time
import uuid
from dataclasses import dataclass, field

from jupyter_client import KernelManager as JCKernelManager


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    error_traceback: str = ""
    result_text: str = ""          # repr of the last expression, if any
    images_png_b64: list = field(default_factory=list)
    timed_out: bool = False


class ManagedKernel:
    """One live Jupyter kernel + the client talking to it."""

    def __init__(self, name: str = "python3"):
        self.km = JCKernelManager(kernel_name=name)
        self.km.start_kernel()
        self.kc = self.km.client()
        self.kc.start_channels()
        # this blocks until the kernel actually says it's alive - skipping it
        # means your first execute_request can get silently dropped
        self.kc.wait_for_ready(timeout=30)

        # write this out so a real JupyterLab instance can attach to the
        # exact same kernel process. this is the whole point of the project.
        self.connection_file = self.km.connection_file

    def interrupt(self):
        self.km.interrupt_kernel()

    def restart(self):
        self.km.restart_kernel(now=True)
        self.kc.wait_for_ready(timeout=30)

    def shutdown(self):
        self.kc.stop_channels()
        self.km.shutdown_kernel(now=True)

    def execute(self, code: str, timeout: float = 30.0) -> ExecResult:
        result = ExecResult()
        msg_id = self.kc.execute(code)

        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                result.timed_out = True
                # don't leave the kernel stuck mid-execution
                self.interrupt()
                break

            try:
                msg = self.kc.get_iopub_msg(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue

            # ignore chatter from other executions if this kernel is ever
            # shared (not currently, but future-proofing costs nothing here)
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue

            msg_type = msg["header"]["msg_type"]
            content = msg["content"]

            if msg_type == "stream":
                if content["name"] == "stdout":
                    result.stdout += content["text"]
                else:
                    result.stderr += content["text"]

            elif msg_type == "execute_result":
                result.result_text = content["data"].get("text/plain", "")

            elif msg_type == "display_data":
                data = content.get("data", {})
                if "image/png" in data:
                    # already base64 in the wire format, no re-encoding needed
                    result.images_png_b64.append(data["image/png"])
                elif "text/plain" in data:
                    result.stdout += data["text/plain"] + "\n"

            elif msg_type == "error":
                # traceback comes with ANSI color codes - strip those before
                # handing it to the model, they just show up as garbage \x1b[...
                raw = "\n".join(content.get("traceback", []))
                result.error_traceback = _strip_ansi(raw)

            elif msg_type == "status" and content["execution_state"] == "idle":
                break

        return result

    def introspect_variables(self) -> str:
        """
        Rather than letting the model run arbitrary introspection code
        (which it could anyway, but let's not tempt fate), run a small
        snippet ourselves and hand back the JSON.
        """
        probe = (
            "import json as _json\n"
            "_out = {}\n"
            "for _k, _v in list(globals().items()):\n"
            "    if _k.startswith('_'):\n"
            "        continue\n"
            "    try:\n"
            "        _out[_k] = {'type': type(_v).__name__, 'repr': repr(_v)[:200]}\n"
            "    except Exception:\n"
            "        _out[_k] = {'type': type(_v).__name__, 'repr': '<unreprable>'}\n"
            "print(_json.dumps(_out))\n"
        )
        res = self.execute(probe, timeout=10.0)
        return res.stdout.strip()


def _strip_ansi(text: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
