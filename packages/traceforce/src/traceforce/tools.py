"""文件工具：四个工厂（read/edit/write/bash）+ 路径逃逸防护 + FileMutationQueue 细粒度并发写锁。"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from pathlib import Path
from subprocess import DEVNULL, PIPE

from traceforce_runtime.tools import Tool, ToolResult  # pyright: ignore[reportMissingImports]

from traceforce.mutation_queue import FileMutationQueue

_TIMEOUT_SECONDS = 120
_DANGEROUS = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
_NON_INTERACTIVE_ENV = {
    "CI": "1",
    "DEBIAN_FRONTEND": "noninteractive",
    "GIT_TERMINAL_PROMPT": "0",
    "PIP_NO_INPUT": "1",
    "npm_config_yes": "true",
    "PAGER": "cat",
    "GIT_PAGER": "cat",
    "EDITOR": "true",
    "VISUAL": "true",
}


def _safe_path(root: Path, p: str) -> Path:
    """把 p（相对或绝对）解析到 root 内，逃逸 → ValueError。"""
    path = (root / p).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def make_read_tool(root: str | Path) -> Tool:
    """read(path, limit=None, offset=None)：精细化读文件（附带行号统计与越界提示）。"""
    root = Path(root).resolve()

    def read(path: str, limit: int | None = None, offset: int | None = None) -> ToolResult:
        """Read file contents with line limits and offset. Use for large files."""
        try:
            fp = _safe_path(root, path)
            if not fp.exists():
                return ToolResult(ok=False, error=f"Error: File '{path}' does not exist.")
            if fp.is_dir():
                return ToolResult(
                    ok=False, error=f"'{path}' is a directory, not a regular file."
                )

            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            total_lines = len(lines)

            start_idx = 0
            if offset is not None:
                if offset > total_lines:
                    return ToolResult(
                        ok=False,
                        error=(
                            f"Offset {offset} is beyond end of file ('{path}' "
                            f"has only {total_lines} lines total)."
                        ),
                    )
                start_idx = max(0, offset - 1)

            selected_lines = lines[start_idx:]
            if limit is not None and limit < len(selected_lines):
                remaining = len(selected_lines) - limit
                selected_lines = selected_lines[:limit] + [
                    f"... ({remaining} more lines, {total_lines} lines total)"
                ]

            return ToolResult(ok=True, data="\n".join(selected_lines)[:50000])
        except Exception as e:
            return ToolResult(ok=False, error=f"Error: {e}")

    return Tool(func=read, name="read", is_parallel_safe=True)


def make_write_tool(
    root: str | Path, mutation_queue: FileMutationQueue | None = None
) -> Tool:
    """write(path, content)：覆盖写（单文件互斥锁保护，天然并发安全）。"""
    root = Path(root).resolve()
    queue = mutation_queue or FileMutationQueue()

    async def write(path: str, content: str) -> ToolResult:
        """Write content to file. Creates/overwrites the file safely."""
        try:
            fp = _safe_path(root, path)
            lock = await queue.get_lock(fp)
            async with lock:
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                line_count = len(content.splitlines())
                return ToolResult(
                    ok=True,
                    data=f"Wrote {len(content)} bytes ({line_count} lines) to {path}",
                )
        except Exception as e:
            return ToolResult(ok=False, error=f"Error writing to '{path}': {e}")

    return Tool(func=write, name="write", is_parallel_safe=False)


def make_edit_tool(
    root: str | Path, mutation_queue: FileMutationQueue | None = None
) -> Tool:
    """edit(path, old_text, new_text)：精确替换一次（单文件互斥锁保护 + 多重匹配与未找到精准提示）。"""
    root = Path(root).resolve()
    queue = mutation_queue or FileMutationQueue()

    async def edit(path: str, old_text: str, new_text: str) -> ToolResult:
        """Replace exact text in file (first unique occurrence only)."""
        try:
            fp = _safe_path(root, path)
            if not fp.exists():
                return ToolResult(ok=False, error=f"Error: File '{path}' does not exist.")
            if fp.is_dir():
                return ToolResult(
                    ok=False, error=f"'{path}' is a directory, not a regular file."
                )

            lock = await queue.get_lock(fp)
            async with lock:
                content = fp.read_text(encoding="utf-8", errors="replace")
                match_count = content.count(old_text)
                total_lines = len(content.splitlines())

                if match_count == 0:
                    return ToolResult(
                        ok=False,
                        error=(
                            f"Text not found in {path} (file has {total_lines} lines total). "
                            "Tip: Check exact whitespace, indentation, and newlines, "
                            f"or call read('{path}') first."
                        ),
                    )

                if match_count > 1:
                    return ToolResult(
                        ok=False,
                        error=(
                            f"Could not edit '{path}': old_text matched {match_count} locations. "
                            "Please provide more surrounding context lines to ensure a unique match."
                        ),
                    )

                new_content = content.replace(old_text, new_text, 1)
                fp.write_text(new_content, encoding="utf-8")
                return ToolResult(
                    ok=True, data=f"Edited {path} successfully (1 replacement made)"
                )
        except Exception as e:
            return ToolResult(ok=False, error=f"Error editing '{path}': {e}")

    return Tool(func=edit, name="edit", is_parallel_safe=False)


def _decode_output(stdout: bytes | None, stderr: bytes | None) -> str:
    return ((stdout or b"") + (stderr or b"")).decode("utf-8", errors="replace").strip()


async def _read_stream(stream: asyncio.StreamReader | None) -> bytes:
    """Drain one subprocess pipe independently of process wait/cancellation."""
    if stream is None:
        return b""
    return await stream.read()


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Terminate the shell and its descendants, then wait for the shell."""
    if os.name == "nt":
        with contextlib.suppress(OSError):
            proc.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=2)
        if proc.returncode is None:
            with contextlib.suppress(OSError):
                proc.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=2)
        # The shell may have exited while a descendant remains in the group.
        # Always attempt the escalation so those descendants cannot hold pipes.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    await proc.wait()


async def _finish_streams(
    stream_tasks: tuple[asyncio.Task[bytes], asyncio.Task[bytes]],
) -> tuple[bytes, bytes]:
    """Collect pipe readers, bounding cleanup for a misbehaving descendant."""
    try:
        return await asyncio.wait_for(asyncio.gather(*stream_tasks), timeout=2)
    except asyncio.TimeoutError:
        for task in stream_tasks:
            task.cancel()
        await asyncio.gather(*stream_tasks, return_exceptions=True)
        return tuple(
            task.result()
            if task.done() and not task.cancelled() and task.exception() is None
            else b""
            for task in stream_tasks
        )  # type: ignore[return-value]


def make_bash_tool(root: str | Path) -> Tool:
    """bash(command)：非交互 shell，禁止继承 stdin，并支持进程组清理。"""
    root = Path(root).resolve()

    async def bash(command: str) -> ToolResult:
        """Run a non-interactive shell command in the workspace root."""
        if any(d in command for d in _DANGEROUS):
            return ToolResult(ok=False, error="Dangerous command blocked")

        cmd_args = (
            ["cmd.exe", "/c", command]
            if os.name == "nt"
            else ["/bin/sh", "-c", command]
        )
        env = os.environ.copy()
        env.update(_NON_INTERACTIVE_ENV)
        kwargs: dict[str, object] = {
            "cwd": root,
            "stdin": DEVNULL,
            "stdout": PIPE,
            "stderr": PIPE,
            "env": env,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        else:
            kwargs["creationflags"] = getattr(
                __import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0
            )

        try:
            proc = await asyncio.create_subprocess_exec(*cmd_args, **kwargs)
            stream_tasks = (
                asyncio.create_task(_read_stream(proc.stdout)),
                asyncio.create_task(_read_stream(proc.stderr)),
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await _terminate_process(proc)
                stdout, stderr = await _finish_streams(stream_tasks)
                captured = _decode_output(stdout, stderr)
                partial_text = (
                    captured[-2000:]
                    if captured
                    else "(no output captured before timeout)"
                )
                return ToolResult(
                    ok=False,
                    error=(
                        f"Timeout ({_TIMEOUT_SECONDS}s) for command '{command}'.\n"
                        f"=== Output before timeout ===\n{partial_text}\n"
                        "=== End of output ===\n"
                        "Tip: Use non-interactive flags (e.g. -y/--no-input) for commands that support them."
                    ),
                )
            except asyncio.CancelledError:
                await _terminate_process(proc)
                await _finish_streams(stream_tasks)
                raise
            else:
                stdout, stderr = await _finish_streams(stream_tasks)

            output = _decode_output(stdout, stderr)
            if proc.returncode:
                return ToolResult(
                    ok=False,
                    error=(
                        f"Command exited with status {proc.returncode}: '{command}'\n"
                        f"{output or '(no output)'}"
                    ),
                )
            return ToolResult(ok=True, data=output[:50000] if output else "(no output)")
        except OSError as exc:
            return ToolResult(ok=False, error=f"Error: {exc}")

    return Tool(func=bash, name="bash", is_parallel_safe=False)
