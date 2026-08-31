"""Textual TUI 的离线行为测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.events import Paste
from textual.widgets import TextArea
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
    TaskInput,
    _STREAM_CHARS_PER_TICK,
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
        conversation = app.query_one("#conversation", ConversationLog)
        assert conversation.transcript == "SYSTEM\nTURN 1"
        app._flush_stream_text()
        assert conversation.transcript == "SYSTEM\nTURN 1\n\nASSISTANT\nhell"
        app.handle_event(ToolExecutionStart("tool-1", "read", {"path": "a.py"}))
        await pilot.pause()
        assert conversation.transcript == "SYSTEM\nTURN 1\n\nASSISTANT\nhello"
        card = app.query_one("#activity #cards ToolCard", ToolCard)
        assert card.title.startswith("RUNNING")
        assert card.query_one("#details", TextArea).text == '{"path":"a.py"}'
        app.handle_event(ToolExecutionEnd("tool-1", "read", "file contents", False))
        await pilot.pause()
        assert card.title.startswith("DONE")
        assert "file contents" in card.query_one("#details", TextArea).text
        app.handle_event(TurnEnd(message=assistant, tool_results=[]))
        assert conversation.transcript.count("ASSISTANT\nhello") == 1
        app.handle_event(AgentEnd([], "hello", 1, "end_turn"))
        assert app._status_text == "end_turn · 1 turns"
        app.exit()


@pytest.mark.anyio
async def test_streaming_tick_is_bounded_and_agent_end_flushes(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assistant = type("Assistant", (), {"content": ""})()
    text = "x" * (_STREAM_CHARS_PER_TICK * 2 + 1)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(TurnStart(iteration=1))
        app.handle_event(MessageUpdate(message=assistant, chunk=StreamChunk(content=text)))
        conversation = app.query_one("#conversation", ConversationLog)
        assert conversation.transcript == "SYSTEM\nTURN 1"
        app._flush_stream_text()
        assert conversation.transcript.endswith("ASSISTANT\n" + "x" * _STREAM_CHARS_PER_TICK)
        app._flush_stream_text()
        assert conversation.transcript.endswith("ASSISTANT\n" + "x" * (_STREAM_CHARS_PER_TICK * 2))
        app.handle_event(AgentEnd([], text, 1, "end_turn"))
        assert conversation.transcript.endswith("ASSISTANT\n" + text)
        assert app._stream_buffer == ""
        app.exit()


@pytest.mark.anyio
async def test_cancelled_agent_end_discards_pending_stream(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assistant = type("Assistant", (), {"content": ""})()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(TurnStart(iteration=1))
        app.handle_event(MessageUpdate(message=assistant, chunk=StreamChunk(content="discard")))
        app.handle_event(AgentEnd([], None, 1, "cancelled"))
        assert "discard" not in app.query_one("#conversation", ConversationLog).transcript
        assert app._stream_buffer == ""
        app.exit()


@pytest.mark.anyio
async def test_empty_chunk_and_non_streaming_turn_end_are_safe(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assistant = type("Assistant", (), {"content": "fallback"})()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(TurnStart(iteration=1))
        app.handle_event(MessageUpdate(message=assistant, chunk=StreamChunk(content="")))
        app.handle_event(TurnEnd(message=assistant, tool_results=[]))
        conversation = app.query_one("#conversation", ConversationLog)
        assert conversation.transcript.endswith("ASSISTANT\nfallback")
        app.exit()


@pytest.mark.anyio
async def test_stream_buffer_is_discarded_on_cancel_and_clear(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assistant = type("Assistant", (), {"content": ""})()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(TurnStart(iteration=1))
        app.handle_event(MessageUpdate(message=assistant, chunk=StreamChunk(content="stale")))
        app.action_cancel_task()
        assert app._stream_buffer == ""
        app._flush_stream_text()
        assert "stale" not in app.query_one("#conversation", ConversationLog).transcript
        app.handle_event(TurnStart(iteration=2))
        app.handle_event(MessageUpdate(message=assistant, chunk=StreamChunk(content="clear-me")))
        app.action_clear_log()
        assert app._stream_buffer == ""
        app._flush_stream_text()
        assert app.query_one("#conversation", ConversationLog).transcript == ""
        app.exit()


@pytest.mark.anyio
async def test_transcript_copy_flushes_pending_stream(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    copied: list[str] = []
    assistant = type("Assistant", (), {"content": ""})()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(TurnStart(iteration=1))
        app.handle_event(MessageUpdate(message=assistant, chunk=StreamChunk(content="pending")))
        app.copy_to_clipboard = copied.append
        app._copy_transcript()
        assert copied == ["SYSTEM\nTURN 1\n\nASSISTANT\npending"]
        assert app._stream_buffer == ""
        app.exit()


@pytest.mark.anyio
async def test_activity_layout_mounts_on_wide_and_narrow_viewports(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    event = ToolExecutionStart("layout-tool", "read", {"path": "a.py"})
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        activity = app.query_one("#activity")
        assert app.query_one("#activity #cards") is not None
        app.handle_event(event)
        await pilot.pause()
        assert app.query_one("#activity #cards ToolCard", ToolCard)
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert app.query_one("#body").has_class("compact")
        assert activity.has_class("compact")
        assert app.query_one("#activity #cards ToolCard", ToolCard)
        app.exit()


@pytest.mark.anyio
async def test_one_shot_task_completes_and_renders_assistant(tmp_path: Path) -> None:
    app = make_app(tmp_path, task="say hello")
    async with app.run_test() as pilot:
        for _ in range(5):
            await pilot.pause()
        conversation = app.query_one("#conversation", ConversationLog)
        assert "hello" in conversation.text
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


@pytest.mark.anyio
async def test_tool_card_clips_large_result(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    event = ToolExecutionStart("x", "read", {"path": "a"})
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(event)
        await pilot.pause()
        card = app.query_one("#activity #cards ToolCard", ToolCard)
        card.finish(ToolExecutionEnd("x", "read", "x" * 3000, False))
        await pilot.pause()
        assert "clipped" in card.query_one("#details", TextArea).text
        app.exit()


@pytest.mark.anyio
async def test_conversation_is_selectable_and_copyable(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    copied: list[str] = []
    async with app.run_test() as pilot:
        await pilot.pause()
        conversation = app.query_one("#conversation", ConversationLog)
        conversation.append_block("SYSTEM", "copy this text")
        conversation.select_all()
        app.copy_to_clipboard = copied.append
        app.action_copy_selection()
        assert copied == [conversation.selected_text]
        assert "copy this text" in copied[0]
        app.exit()


@pytest.mark.anyio
async def test_task_input_merges_multiline_paste_without_submitting(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TaskInput)
        prompt.post_message(Paste("第一行\r\n第二行\n第三行"))
        await pilot.pause()
        assert prompt.value == "第一行 第二行 第三行"
        assert app._run_task is None
        app.exit()


@pytest.mark.anyio
async def test_task_input_paste_preserves_existing_cursor_position(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TaskInput)
        prompt.value = "beforeafter"
        prompt.cursor_position = 6
        prompt.post_message(Paste(" middle "))
        await pilot.pause()
        assert prompt.value == "before middle after"
        app.exit()


@pytest.mark.anyio
async def test_transcript_can_be_copied_and_saved(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    copied: list[str] = []
    async with app.run_test() as pilot:
        await pilot.pause()
        conversation = app.query_one("#conversation", ConversationLog)
        conversation.append_block("SYSTEM", "visible error")
        original_transcript = conversation.transcript
        app.copy_to_clipboard = copied.append
        app._copy_transcript()
        path = app._save_transcript()
        assert copied == [original_transcript]
        assert path is not None
        assert path.read_text(encoding="utf-8").strip() == original_transcript
        app.exit()


@pytest.mark.anyio
async def test_agent_error_is_visible_and_saved(tmp_path: Path) -> None:
    class FailingLLM:
        async def achat_stream(self, *, messages, tools=None, **kwargs):
            del messages, tools, kwargs
            raise RuntimeError("model unavailable")
            yield  # pragma: no cover

    app = make_app(tmp_path, llm=FailingLLM())
    async with app.run_test() as pilot:
        await pilot.pause()
        app._submit_text("trigger error")
        for _ in range(5):
            await pilot.pause()
        conversation = app.query_one("#conversation", ConversationLog)
        assert "RuntimeError: model unavailable" in conversation.transcript
        error_path = tmp_path / ".traceforce" / "tui-error.txt"
        assert error_path.is_file()
        assert "RuntimeError: model unavailable" in error_path.read_text(encoding="utf-8")
        app.exit()

@pytest.mark.anyio
async def test_tool_card_can_close_without_affecting_task(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    event = ToolExecutionStart("tool-1", "read", {"path": "a.py"})
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_event(event)
        await pilot.pause()
        card = app.query_one("#activity #cards ToolCard", ToolCard)
        card.post_message(ToolCard.Closed(card))
        await pilot.pause()
        assert not app.query("#cards ToolCard")
        assert "tool-1" not in app._current_cards
        app.handle_event(ToolExecutionEnd("tool-1", "read", "late", False))
        app.exit()
