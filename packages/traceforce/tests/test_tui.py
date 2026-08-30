"""Textual TUI 的离线行为测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from traceforce_llm import Response, StreamChunk
from traceforce_runtime.events import (
    AgentEnd,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from traceforce_runtime.session import Session
from traceforce_runtime.session_store import SessionStore

from traceforce.agent import CodingAgent
from traceforce.cli import build_parser
from traceforce.identity import (
    DEVELOPER_HANDLE,
    DEVELOPER_NAME,
    PRODUCT_NAME,
    PURPOSE,
    TAGLINE,
    WORKFLOW,
)
from traceforce.tui import (
    ConversationLog,
    PermissionDialog,
    ToolCard,
    TraceForceApp,
    TUIPermissionController,
)


class FakeLLM:
    def __init__(self, chunks: list[StreamChunk | Response]) -> None:
        self.chunks = list(chunks)

    async def achat_stream(self, *, messages, tools=None, **kwargs):
        del messages, tools, kwargs
        item = self.chunks.pop(0)
        yield item


def make_app(tmp_path: Path, *, llm: object | None = None, task: str | None = None) -> TraceForceApp:
    session = Session(path=tmp_path / "session.jsonl", cwd=str(tmp_path))
    agent = CodingAgent(
        workspace=tmp_path,
        llm=llm or FakeLLM([StreamChunk(content="hello")]),
        session=session,
        extension_dirs=[],
        max_iterations=3,
    )
    return TraceForceApp(
        agent=agent,
        workspace=tmp_path,
        session_id=session.id,
        session_store=SessionStore(workspace=tmp_path),
        assume_yes=True,
        task=task,
    )


@pytest.mark.anyio
async def test_app_mounts_with_workspace_and_session(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        side = str(app.query_one("#side").render())
        assert PRODUCT_NAME in side
        assert TAGLINE in side
        assert PURPOSE in side
        assert DEVELOPER_NAME in side
        assert DEVELOPER_HANDLE in side
        assert WORKFLOW in side
        assert str(tmp_path) in side
        assert app.session_id in side
        assert app.query_one("#prompt") is not None
        app.exit()


@pytest.mark.anyio
async def test_streaming_and_tool_events_render_cards(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assistant = type("Assistant", (), {"content": "hello"})()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(TurnStart(iteration=1))
        app.handle_event(
            MessageUpdate(message=assistant, chunk=StreamChunk(content="hel"))
        )
        app.handle_event(
            MessageUpdate(message=assistant, chunk=StreamChunk(content="lo"))
        )
        app.handle_event(ToolExecutionStart("tool-1", "read", {"path": "a.py"}))
        await pilot.pause()
        card = app.query_one("#cards ToolCard", ToolCard)
        assert "RUNNING" in str(card.render())
        app.handle_event(ToolExecutionEnd("tool-1", "read", "file contents", False))
        await pilot.pause()
        assert "DONE" in str(card.render())
        assert "file contents" in str(card.render())
        app.handle_event(TurnEnd(message=assistant, tool_results=[]))
        app.handle_event(AgentEnd([], "hello", 1, "end_turn"))
        assert app._status_text == "end_turn · 1 turns"
        app.exit()


@pytest.mark.anyio
async def test_one_shot_task_completes_and_renders_assistant(tmp_path: Path) -> None:
    app = make_app(tmp_path, task="say hello")
    async with app.run_test() as pilot:
        for _ in range(5):
            await pilot.pause()
        conversation = app.query_one("#conversation", ConversationLog)
        assert any("hello" in str(child.render()) for child in conversation.children)
        assert app._run_task is None
        assert app._status_text == "idle"
        app.exit()


@pytest.mark.anyio
async def test_permission_modal_resolves_without_blocking_loop(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    app.assume_yes = False
    controller = TUIPermissionController(app)
    event = ToolExecutionStart("tool-1", "bash", {"command": "pytest -q"})
    async with app.run_test() as pilot:
        await pilot.pause()
        request = asyncio.create_task(app.request_permission(event, controller))
        await asyncio.sleep(0)
        for _ in range(5):
            await pilot.pause()
            if isinstance(app.screen, PermissionDialog):
                break
        assert isinstance(app.screen, PermissionDialog)
        await pilot.click("#allow")
        await pilot.pause()
        assert await request is True
        app.exit()


@pytest.mark.anyio
async def test_cancel_calls_abort_and_returns_to_idle(tmp_path: Path) -> None:
    class BlockingLLM:
        async def achat_stream(self, *, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            await asyncio.Event().wait()
            yield StreamChunk(content="never")

    app = make_app(tmp_path, llm=BlockingLLM())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._submit_text("long task")
        await pilot.pause()
        assert app._run_task is not None
        app.action_cancel_task()
        for _ in range(3):
            await pilot.pause()
        assert app._run_task is None
        assert app._status_text == "cancelled"
        app.exit()


def test_parser_supports_tui_flag() -> None:
    args = build_parser().parse_args(["--tui", "task"])
    assert args.tui is True
    assert args.prompt == "task"


def test_tool_card_clips_large_result(tmp_path: Path) -> None:
    event = ToolExecutionStart("x", "read", {"path": "a"})
    card = ToolCard(event)
    card.finish(ToolExecutionEnd("x", "read", "x" * 3000, False))
    assert "clipped" in str(card.render())
