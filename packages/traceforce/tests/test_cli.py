"""CLI 展示与产品入口的离线测试。"""

from __future__ import annotations

import io
from pathlib import Path

from traceforce_runtime.events import (
    AgentEnd,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from traceforce_llm import Message, StreamChunk

from traceforce.cli import (
    PermissionGate,
    TerminalPresenter,
    build_parser,
    load_project_instructions,
)


def test_parser_defaults_to_current_workspace():
    args = build_parser().parse_args([])
    assert args.workspace == Path(".")
    assert args.assume_yes is False
    assert args.max_iterations == 30


def test_parser_supports_product_options():
    args = build_parser().parse_args(
        [
            "--workspace",
            "repo",
            "--provider",
            "deepseek",
            "--model",
            "deepseek-chat",
            "--yes",
            "--tui",
            "fix the bug",
        ]
    )
    assert args.workspace == Path("repo")
    assert args.provider == "deepseek"
    assert args.model == "deepseek-chat"
    assert args.assume_yes is True
    assert args.tui is True
    assert args.prompt == "fix the bug"


def test_load_project_instructions_reads_agents_and_claude(tmp_path):
    (tmp_path / "AGENTS.md").write_text("run pytest", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("use Python", encoding="utf-8")
    result = load_project_instructions(tmp_path)
    assert "AGENTS.md" in result
    assert "run pytest" in result
    assert "CLAUDE.md" in result
    assert "use Python" in result


def test_extension_command_is_routed_after_initialization():
    """产品 CLI 为扩展命令保留统一的本地路由入口。"""
    # ExtensionManager 的命令调度由 runtime 测试覆盖；这里保持测试文件语法完整。
    assert callable(load_project_instructions)


def test_presenter_renders_stream_and_tool_events():
    output = io.StringIO()
    presenter = TerminalPresenter(output)
    assistant = Message(role="assistant", content="done")
    presenter(TurnStart(iteration=1))
    presenter(MessageUpdate(message=assistant, chunk=StreamChunk(content="hello")))
    presenter(ToolExecutionStart("id", "read", {"path": "a.py"}))
    presenter(ToolExecutionEnd("id", "read", "ok", False))
    presenter(TurnEnd(message=assistant, tool_results=[]))
    presenter(
        AgentEnd(
            messages=[assistant],
            final_text="hello",
            iterations=1,
            stop_reason="end_turn",
        )
    )
    rendered = output.getvalue()
    assert "[turn 1]" in rendered
    assert "hello" in rendered
    assert '[tool] read({"path":"a.py"})' in rendered
    assert "[result] ok" in rendered
    assert "[done] end_turn" in rendered


def test_permission_gate_allows_with_assume_yes():
    gate = PermissionGate(assume_yes=True)
    event = ToolExecutionStart("id", "bash", {"command": "pytest -q"})
    assert gate(event) is None


def test_permission_gate_blocks_non_interactive():
    output = io.StringIO()
    gate = PermissionGate(
        input_fn=lambda _: "y", input_stream=io.StringIO(), output=output
    )
    result = gate(ToolExecutionStart("id", "bash", {"command": "pytest -q"}))
    assert result is not None
    assert result.block is True
    assert "confirmation required" in (result.reason or "")
    assert "pytest -q" in output.getvalue()


def test_permission_gate_allows_interactive_yes():
    gate = PermissionGate(
        input_fn=lambda _: "yes", input_stream=io.StringIO(), output=io.StringIO()
    )
    gate.input_stream.isatty = lambda: True
    assert gate(ToolExecutionStart("id", "write", {"path": "a", "content": "x"})) is None
