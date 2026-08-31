"""终端产品入口：当前目录启动、流式输出、权限确认与会话命令。"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import signal
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from dotenv import load_dotenv
from traceforce_runtime.events import (
    AgentEnd,
    HookResult,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from traceforce_runtime.session_store import SessionStore
from traceforce_llm import Config, LLM

from traceforce.agent import CodingAgent
from traceforce.identity import (
    DEVELOPER_HANDLE,
    DEVELOPER_NAME,
    PRODUCT_NAME,
    PURPOSE,
    TAGLINE,
    VERSION,
    WORKFLOW,
)


DEFAULT_SYSTEM_PROMPT = f"""你是 {PRODUCT_NAME}，由 {DEVELOPER_NAME} 开发。

{PURPOSE}

请自主完成用户交给你的编程任务：先阅读相关文件和项目说明，再设计并实施最小必要修改，
最后运行合适的测试或检查命令验证结果。工具返回错误时请分析错误并继续修复，不要猜测文件内容。
除非用户明确要求，否则不要修改工作区之外的文件，也不要泄露环境变量、API key 或其他凭据。
默认使用与用户相同的语言回复；用户使用中文时，任务分析、进度说明和最终总结均使用中文，
代码、命令、路径和必要的技术标识符可保留原文。
完成任务时总结修改了什么、验证了什么，以及仍然存在的风险。执行 shell 命令时必须优先使用非交互模式；安装依赖、初始化项目或执行可能请求用户输入的命令时，主动使用 `--yes`、`-y`、`--no-input` 或等价参数，不要启动持续等待人工 stdin 的命令。运行安装、构建等耗时命令时，不要使用 `tail` 等会等到进程结束才显示结果的管道过滤器。"""


class TerminalPresenter:
    """把 Agent 生命周期事件渲染为稳定的纯终端输出。"""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self._turn_streamed_text = False
        self._line_open = False

    def reset(self) -> None:
        """开始下一次 REPL 任务时清理展示状态。"""
        self._turn_streamed_text = False
        self._line_open = False

    def __call__(self, event: Any) -> None:
        """同步 hook：只观察事件，不改变 Agent 决策。"""
        if isinstance(event, TurnStart):
            self._turn_streamed_text = False
            self._finish_line()
            self._write(f"\n[turn {event.iteration}]\n")
        elif isinstance(event, MessageUpdate):
            content = getattr(event.chunk, "content", "") or ""
            if content:
                self._write(content)
                self._turn_streamed_text = True
                self._line_open = True
        elif isinstance(event, ToolExecutionStart):
            self._finish_line()
            self._write(f"[tool] {event.tool_name}({self._format_args(event.args)})\n")
        elif isinstance(event, ToolExecutionEnd):
            self._finish_line()
            result = self._clip(event.result, 4000)
            self._write(f"[result{' error' if event.is_error else ''}] {result}\n")
        elif isinstance(event, TurnEnd):
            if event.message.content and not self._turn_streamed_text:
                self._finish_line()
                self._write(event.message.content)
                self._line_open = True
            self._finish_line()
        elif isinstance(event, AgentEnd):
            self._finish_line()
            self._write(
                f"[done] {event.stop_reason}; iterations={event.iterations}\n"
            )

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def _finish_line(self) -> None:
        if self._line_open:
            self._write("\n")
            self._line_open = False

    @staticmethod
    def _format_args(args: dict[str, Any]) -> str:
        try:
            return json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return repr(args)

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n... <{len(text) - limit} chars clipped>"


class PermissionGate:
    """在危险工具执行前请求人工确认，非交互环境默认拒绝。"""

    CONFIRMABLE_TOOLS = frozenset({"bash", "write", "edit"})

    def __init__(
        self,
        *,
        assume_yes: bool = False,
        input_fn: Callable[[str], str] | None = None,
        input_stream: TextIO | None = None,
        output: TextIO | None = None,
    ) -> None:
        self.assume_yes = assume_yes
        self.input_fn = input_fn or input
        self.input_stream = input_stream or sys.stdin
        self.output = output or sys.stdout

    def __call__(self, event: ToolExecutionStart) -> HookResult | None:
        """返回 None 放行，返回 HookResult(block=True) 拒绝。"""
        if event.tool_name not in self.CONFIRMABLE_TOOLS or self.assume_yes:
            return None

        self.output.write(self._describe(event))
        self.output.flush()
        if not self._is_interactive():
            return HookResult(
                block=True,
                reason="confirmation required; rerun with --yes in a trusted environment",
            )
        try:
            answer = self.input_fn("Allow this tool call? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            self.output.write("denied\n")
            return HookResult(block=True, reason="permission prompt interrupted")
        if answer.strip().lower() in {"y", "yes"}:
            return None
        return HookResult(block=True, reason="permission denied by user")

    def _is_interactive(self) -> bool:
        try:
            return bool(self.input_stream.isatty())
        except (AttributeError, OSError):
            return False

    @staticmethod
    def _describe(event: ToolExecutionStart) -> str:
        args = event.args
        if event.tool_name == "bash":
            return f"\n[confirm] bash: {args.get('command', '')}\n"
        if event.tool_name == "write":
            content = str(args.get("content", ""))
            preview = content[:600]
            suffix = "..." if len(content) > 600 else ""
            return (
                f"\n[confirm] write {args.get('path', '')} "
                f"({len(content)} chars):\n{preview}{suffix}\n"
            )
        old_text = str(args.get("old_text", ""))
        new_text = str(args.get("new_text", ""))
        return (
            f"\n[confirm] edit {args.get('path', '')}: "
            f"replace {len(old_text)} chars with {len(new_text)} chars\n"
        )


def load_project_instructions(workspace: Path) -> str:
    """读取工作区级 AGENTS.md/CLAUDE.md，作为产品 system prompt 的补充。"""
    sections: list[str] = []
    for filename in ("AGENTS.md", "CLAUDE.md"):
        path = workspace / filename
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if content:
            sections.append(f"<PROJECT_INSTRUCTIONS path=\"{filename}\">\n{content[:20000]}\n</PROJECT_INSTRUCTIONS>")
    return "\n\n".join(sections)


def build_llm(args: argparse.Namespace) -> LLM:
    """从环境变量构造 LLM；凭据只从环境读取，不接受命令行明文 key。"""
    provider = (args.provider or os.getenv("TRACEFORCE_PROVIDER") or "openai").lower()
    prefix = provider.upper()
    api_key = os.getenv(f"{prefix}_API_KEY") or os.getenv("TRACEFORCE_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"Missing {prefix}_API_KEY. Put it in {args.workspace / '.env'} or export it in the shell."
        )

    model = (
        args.model
        or os.getenv("TRACEFORCE_MODEL")
        or os.getenv(f"{prefix}_MODEL")
    )
    if not model:
        raise RuntimeError(
            f"Missing model. Set TRACEFORCE_MODEL or {prefix}_MODEL in the environment."
        )

    base_url = args.base_url or os.getenv("TRACEFORCE_BASE_URL") or os.getenv(f"{prefix}_BASE_URL")
    options: dict[str, Any] = {
        "provider": provider,
        "api_key": api_key,
        "model": model,
        "timeout": args.timeout,
        "max_retries": args.max_retries,
    }
    if base_url:
        options["base_url"] = base_url
    if args.max_tokens is not None:
        options["max_tokens"] = args.max_tokens
    return LLM(config=Config(**options))


def build_parser() -> argparse.ArgumentParser:
    """构造产品 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="traceforce",
        description=f"{PRODUCT_NAME}：{TAGLINE}。",
        epilog=f"由 {DEVELOPER_NAME}（GitHub: {DEVELOPER_HANDLE}）独立开发。",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="工作区目录，默认是当前目录",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="一次性任务；省略后进入交互式 REPL",
    )
    parser.add_argument("--session", help="恢复指定会话 ID 或唯一前缀")
    parser.add_argument("--provider", help="模型供应商，默认读取 TRACEFORCE_PROVIDER/openai")
    parser.add_argument("--model", help="模型名，默认读取 TRACEFORCE_MODEL 或 PROVIDER_MODEL")
    parser.add_argument("--base-url", help="OpenAI 兼容网关地址")
    parser.add_argument("--timeout", type=int, default=120, help="单次模型请求超时秒数")
    parser.add_argument("--max-retries", type=int, default=3, help="模型请求最大重试次数")
    parser.add_argument("--max-tokens", type=int, default=None, help="模型输出 token 上限")
    parser.add_argument(
        "--yes",
        "--no-confirm",
        dest="assume_yes",
        action="store_true",
        help="跳过 bash/write/edit 确认（仅在信任工作区时使用）",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=30,
        help="限制一次任务的 Agent 迭代次数，默认 30",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="使用 Textual 全屏界面（默认仍使用纯终端模式）",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def _print_help() -> None:
    print(
        "命令：\n"
        "  /help       显示本帮助\n"
        "  /session    显示当前工作区和会话\n"
        "  /sessions   列出已保存会话\n"
        "  /clear      清空当前会话并保留配置\n"
        "  /exit       退出\n"
        "普通文本会交给 Agent 自主完成。"
    )


def _print_sessions(store: SessionStore) -> None:
    metas = store.list()
    if not metas:
        print("（暂无已保存会话）")
        return
    for meta in metas:
        print(f"{meta.id}\t{meta.entries} entries\t{meta.created_at}")


async def _run_turn(agent: CodingAgent, user_input: str) -> str | None:
    """运行一轮并在 Unix 上让 Ctrl+C 触发 Agent.abort()。"""
    loop = asyncio.get_running_loop()
    installed = False
    try:
        loop.add_signal_handler(signal.SIGINT, agent.agent.abort)
        installed = True
    except (NotImplementedError, RuntimeError, AttributeError):
        pass
    try:
        return await agent.run(user_input)
    except asyncio.CancelledError:
        agent.agent.abort()
        return "(cancelled)"
    finally:
        if installed:
            loop.remove_signal_handler(signal.SIGINT)


async def async_main(args: argparse.Namespace) -> None:
    """CLI 异步主循环。"""
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"Workspace is not a directory: {workspace}")
    args.workspace = workspace
    load_dotenv(workspace / ".env")

    llm = build_llm(args)
    store = SessionStore(workspace=workspace)
    session = store.open(args.session) if args.session else store.create()
    instructions = load_project_instructions(workspace)
    system_prompt = DEFAULT_SYSTEM_PROMPT
    if instructions:
        system_prompt += f"\n\n{instructions}"

    presenter = TerminalPresenter()
    permission = PermissionGate(assume_yes=args.assume_yes)
    agent = CodingAgent(
        workspace=workspace,
        llm=llm,
        session=session,
        system_prompt=system_prompt,
        max_iterations=args.max_iterations,
        extension_dirs=[
            workspace / ".agents" / "extensions",
            Path(__file__).with_name("mcp.py"),
        ],
        hooks=[
            (TurnStart, presenter),
            (MessageUpdate, presenter),
            (ToolExecutionStart, presenter),
            (ToolExecutionStart, permission),
            (ToolExecutionEnd, presenter),
            (TurnEnd, presenter),
            (AgentEnd, presenter),
        ],
    )
    try:
        await agent.agent.ensure_initialized()

        print(f"{PRODUCT_NAME} v{VERSION}")
        print(f"{TAGLINE}")
        print(f"developer: {DEVELOPER_NAME} (GitHub: {DEVELOPER_HANDLE})")
        print(f"workflow: {WORKFLOW}")
        print(f"workspace: {workspace}")
        print(f"session:   {session.id}")
        print("输入 /help 查看命令；输入 /exit 退出。")

        if args.prompt:
            result = await _run_turn(agent, args.prompt)
            if result is None:
                print("[warning] 达到 max_iterations，尚未得到最终回答。")
            return

        while True:
            try:
                raw = input("\nyou> ").strip()
            except EOFError:
                print()
                return
            except KeyboardInterrupt:
                print("\n（已取消输入）")
                continue
            if not raw:
                continue
            if raw in {"/exit", "/quit", "exit", "quit"}:
                return
            if raw == "/help":
                _print_help()
                continue
            if raw == "/session":
                print(f"workspace: {workspace}\nsession: {session.id}")
                continue
            if raw == "/sessions":
                _print_sessions(store)
                continue
            if raw == "/clear":
                agent.agent.reset()
                presenter.reset()
                print("（当前会话已清空）")
                continue
            if raw.startswith("/"):
                command, _, command_args = raw[1:].partition(" ")
                try:
                    result = agent.agent.extension_manager.handle_command(
                        command, command_args or None
                    )
                    if inspect.isawaitable(result):
                        result = await result
                except ValueError as exc:
                    print(f"[error] {exc}")
                else:
                    if result is not None:
                        print(result)
                continue
            try:
                result = await _run_turn(agent, raw)
                if result is None:
                    print("[warning] 达到 max_iterations，尚未得到最终回答。")
            except KeyboardInterrupt:
                agent.agent.abort()
                print("\n（任务已取消，未完成的流式内容不会写入会话）")
            except Exception as exc:
                print(f"[error] {exc}", file=sys.stderr)
    finally:
        await agent.agent.extension_manager.close()


def main(argv: Sequence[str] | None = None) -> None:
    """console script 入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.tui:
            from traceforce.tui import run_tui

            run_tui(args)
        else:
            asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\n再见。")
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
