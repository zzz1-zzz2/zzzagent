"""TraceForce Textual 全屏界面：对话、工具卡片、权限确认与会话控制。"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Paste
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Footer, Header, Input, Label, Static, TextArea

from traceforce_runtime.events import (
    AgentEnd,
    AgentStart,
    HookResult,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from traceforce_runtime.session import Session
from traceforce_runtime.session_store import SessionStore

from traceforce.agent import CodingAgent
from traceforce.cli import (
    DEFAULT_SYSTEM_PROMPT,
    build_llm,
    load_project_instructions,
)
from traceforce.identity import (
    DEVELOPER_HANDLE,
    DEVELOPER_NAME,
    PRODUCT_NAME,
    PURPOSE,
    TAGLINE,
    WORKFLOW,
)


_STREAM_TICK_SECONDS = 0.08
_STREAM_CHARS_PER_TICK = 4


class TaskInput(Input):
    """将终端多行粘贴内容安全合并为一条任务输入。"""

    def _on_paste(self, event: Paste) -> None:
        text = event.text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\n", " ")
        if text:
            self.insert_text_at_cursor(text)
        event.prevent_default()
        event.stop()


class ToolCard(Collapsible):
    """显示一个可折叠、可复制、可关闭的工具调用记录。"""

    class Closed(Message):
        """请求产品层移除卡片的可见内容，不影响实际工具执行。"""

        def __init__(self, card: ToolCard) -> None:
            self.card = card
            super().__init__()

    def __init__(self, event: ToolExecutionStart) -> None:
        self.tool_call_id = event.tool_call_id
        self.tool_name = event.tool_name
        self._started_at = time.monotonic()
        self._details = _format_args(event.args)
        self._state = "running"
        self._title_text_value = self._title_text("RUNNING")
        super().__init__(
            TextArea(
                self._details,
                read_only=True,
                soft_wrap=True,
                id="details",
                classes="tool-details",
            ),
            Horizontal(
                Button("Copy details", id="copy"),
                Button("Close", variant="default", id="close"),
                classes="tool-actions",
            ),
            title=self._title_text("RUNNING"),
            collapsed=False,
            classes="tool-card running",
        )

    def finish(self, event: ToolExecutionEnd) -> None:
        """将卡片从运行态更新为成功或错误态，并自动折叠详情。"""
        status = "ERROR" if event.is_error else "DONE"
        elapsed = time.monotonic() - self._started_at
        self._state = "error" if event.is_error else "success"
        self.remove_class("running")
        self.add_class(self._state)
        self._details = f"{self._details}\n\nRESULT\n{_clip(event.result, 2400)}"
        self._title_text_value = self._title_text(status, elapsed)
        self.title = self._title_text_value
        self.collapsed = True
        self._update_details()

    def block(self, reason: str) -> None:
        """显示权限拒绝等未进入实际执行阶段的调用。"""
        elapsed = time.monotonic() - self._started_at
        self._state = "blocked"
        self.remove_class("running")
        self.add_class("blocked")
        self._details = f"{self._details}\n\nBLOCKED\n{_clip(reason, 1200)}"
        self.title = self._title_text("BLOCKED", elapsed)
        self.collapsed = True
        self._update_details()

    def cancel(self) -> None:
        """标记尚未结束的工具调用已被用户取消。"""
        if self._state != "running":
            return
        elapsed = time.monotonic() - self._started_at
        self._state = "cancelled"
        self.remove_class("running")
        self.add_class("cancelled")
        self._details = f"{self._details}\n\nCANCELLED\nTool execution cancelled by user."
        self.title = self._title_text("CANCELLED", elapsed)
        self.collapsed = True
        self._update_details()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.post_message(self.Closed(self))
        elif event.button.id == "copy":
            self.app.copy_to_clipboard(self._details)

    def _update_details(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#details", TextArea).load_text(self._details)

    def _title_text(self, status: str, elapsed: float | None = None) -> str:
        suffix = f"  ({elapsed:.1f}s)" if elapsed is not None else ""
        return f"{status}  {self.tool_name}{suffix}"


class ConversationLog(TextArea):
    """只读、可选中的对话区，assistant token 会更新同一份文本。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("soft_wrap", True)
        super().__init__("", *args, **kwargs)
        self._transcript = ""
        self._assistant_open = False

    def append_block(self, label: str, text: str, *, classes: str = "system") -> None:
        """追加一个 user/system 消息块。"""
        del classes  # TextArea 使用统一的只读选区样式。
        self._finish_assistant()
        self._append_block(f"{label}\n{text}")

    def start_assistant(self) -> None:
        """开始一条可增量更新的 assistant 消息。"""
        self._finish_assistant()
        prefix = "\n\n" if self._transcript else ""
        prefix += "ASSISTANT\n"
        self._append_text(prefix)
        self._assistant_open = True

    def assistant_chunk(self, text: str) -> None:
        """把 token 追加到当前 assistant 消息，而不是制造大量孤立控件。"""
        if not text:
            return
        if not self._assistant_open:
            self.start_assistant()
        self._append_text(text)

    def assistant_message(self, text: str) -> None:
        """渲染非流式模型返回的完整 assistant 消息。"""
        self.start_assistant()
        self.assistant_chunk(text)
        self._finish_assistant()

    def finish_assistant(self) -> None:
        """结束当前 assistant 消息，等待下一轮或下一条消息。"""
        self._finish_assistant()

    @property
    def transcript(self) -> str:
        """返回当前可见对话，供复制和导出使用。"""
        return self._transcript

    def clear_transcript(self) -> None:
        """清除所有消息并重置增量状态。"""
        self._transcript = ""
        self._assistant_open = False
        self.load_text("")

    def _append_block(self, text: str) -> None:
        prefix = "\n\n" if self._transcript else ""
        self._append_text(prefix + text)

    def _append_text(self, text: str) -> None:
        """仅在文档末尾插入新增内容，避免流式输出触发全屏重绘。"""
        if not text:
            return
        self._transcript += text
        self.insert(text, self.document.end, maintain_selection_offset=False)
        self.scroll_end(animate=False)

    def _finish_assistant(self) -> None:
        self._assistant_open = False


class PermissionDialog(ModalScreen[bool]):
    """Textual 内的非阻塞工具权限确认窗口。"""

    BINDINGS = [Binding("escape", "deny", "Deny", show=False)]

    def __init__(self, event: ToolExecutionStart) -> None:
        super().__init__(classes="permission-dialog")
        self.event = event

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("ALLOW TOOL CALL?", classes="permission-title", markup=False),
            Static(_permission_description(self.event), classes="permission-body", markup=False),
            Horizontal(
                Button("Allow", variant="success", id="allow"),
                Button("Deny", variant="error", id="deny"),
                classes="permission-actions",
            ),
            id="permission-box",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "allow")

    def action_deny(self) -> None:
        self.dismiss(False)


class TUIPermissionController:
    """把 runtime 的异步 ToolExecutionStart hook 接到 Textual modal。"""

    def __init__(self, app: TraceForceApp | None = None) -> None:
        self.app = app
        self._future: asyncio.Future[bool] | None = None
        self._screen: PermissionDialog | None = None

    def bind(self, app: TraceForceApp) -> None:
        self.app = app

    async def __call__(self, event: ToolExecutionStart) -> HookResult | None:
        if event.tool_name not in {"bash", "write", "edit"}:
            return None
        if self.app is None or self.app.assume_yes:
            return None

        try:
            allowed = await self.app.request_permission(event, self)
        except asyncio.CancelledError:
            self.app.mark_tool_blocked(event, "permission request cancelled")
            raise
        if allowed:
            return None
        reason = "permission denied by user"
        self.app.mark_tool_blocked(event, reason)
        return HookResult(block=True, reason=reason)

    def cancel(self) -> None:
        """关闭当前弹窗并拒绝请求；供 Ctrl+C 和退出流程使用。"""
        screen = self._screen
        if screen is not None:
            screen.dismiss(False)


class TraceForceApp(App[None]):
    """TraceForce 全屏 TUI。Agent loop 仍完全由 traceforce-runtime 驱动。"""

    TITLE = "TraceForce Coding Agent"
    CSS = """
    Screen {
        background: #10141b;
        color: #e6edf3;
    }
    Header {
        background: #17202b;
        color: #e6edf3;
    }
    Footer {
        background: #17202b;
    }
    #body {
        height: 1fr;
    }
    #body.compact {
        layout: vertical;
    }
    #main {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    #activity {
        width: 34;
        min-width: 24;
        height: 1fr;
        padding: 0 1 1 0;
    }
    .transcript-actions {
        height: auto;
        align: right middle;
        padding: 0 1;
    }
    .transcript-actions Button {
        margin-left: 1;
    }
    #side {
        height: auto;
        max-height: 18;
        border: round #2d3a49;
        padding: 1;
        margin-bottom: 1;
        color: #9fb0c3;
        overflow-y: auto;
    }
    #conversation {
        height: 1fr;
        border: round #2d3a49;
        padding: 1;
        scrollbar-size: 1 1;
    }
    #activity.compact {
        width: 1fr;
        height: 10;
        min-width: 0;
        padding: 0 1 1 1;
        layout: horizontal;
    }
    #activity.compact #side {
        width: 30;
        max-height: 1fr;
        margin: 0 1 0 0;
    }
    #activity.compact #cards {
        width: 1fr;
        height: 1fr;
    }
    .message-block {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    .tool-card {
        background: #1c2530;
        color: #f2d58a;
    }
    .tool-card > .collapsible--title {
        padding: 0 1;
    }
    .tool-card .tool-details {
        height: auto;
        max-height: 18;
        border: round #2d3a49;
        background: #151d27;
    }
    .tool-actions {
        height: auto;
        align: right middle;
        padding-top: 1;
    }
    .tool-actions Button {
        margin-left: 1;
    }
    .tool-card.running {
        border: round #c99a2e;
    }
    .tool-card.success {
        border: round #3fb950;
        color: #b6f0be;
    }
    .tool-card.error {
        border: round #f85149;
        color: #ffb4ad;
    }
    .tool-card.blocked,
    .tool-card.cancelled {
        border: round #9b6baf;
        color: #d8b4e8;
    }
    #prompt {
        dock: bottom;
        margin: 0 1;
        border: round #4f9cf5;
        background: #151d27;
    }
    #status {
        height: 1;
        padding: 0 1;
        color: #9fb0c3;
    }
    PermissionDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.65);
    }
    #permission-box {
        width: 70;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        border: round #4f9cf5;
        background: #17202b;
    }
    .permission-title {
        color: #f2d58a;
        text-style: bold;
        padding-bottom: 1;
    }
    .permission-body {
        max-height: 16;
        overflow-y: auto;
        color: #e6edf3;
    }
    .permission-actions {
        height: auto;
        align: right middle;
        padding-top: 1;
    }
    .permission-actions Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_or_copy", "Cancel / Copy", priority=True),
        Binding("ctrl+shift+c", "copy_selection", "Copy selection"),
        Binding("ctrl+l", "clear_log", "Clear log"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        agent: CodingAgent,
        workspace: Path,
        session_id: str,
        session_store: SessionStore,
        assume_yes: bool = False,
        task: str | None = None,
        agent_factory: Callable[[Session], CodingAgent] | None = None,
        permission_controller: TUIPermissionController | None = None,
    ) -> None:
        super().__init__()
        self.agent = agent
        self.workspace = workspace
        self.session_id = session_id
        self.session_store = session_store
        self.assume_yes = assume_yes
        self.initial_task = task
        self.agent_factory = agent_factory
        self.permission_controller = permission_controller
        self._run_task: asyncio.Task[Any] | None = None
        self._command_task: asyncio.Task[Any] | None = None
        self._current_cards: dict[str, ToolCard] = {}
        self._streaming_turn = False
        self._turn_had_streamed_text = False
        self._stream_events_enabled = False
        self._stream_buffer = ""
        self._stream_flush_timer: Any = None
        self._finish_stream_after_flush = False
        self._compact_activity = False
        self._last_result: str | None = None
        self._status_text = "idle"
        self._permission_future: asyncio.Future[bool] | None = None
        self._permission_screen: PermissionDialog | None = None

    @property
    def is_busy(self) -> bool:
        """当前是否正在运行 Agent 或处理一个 UI 命令。"""
        return self._run_task is not None or self._command_task is not None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="main"):
                yield ConversationLog(id="conversation")
                yield Horizontal(
                    Button("Copy output", id="copy-transcript"),
                    Button("Save output", id="save-transcript"),
                    classes="transcript-actions",
                )
                yield Label("idle", id="status")
                yield TaskInput(
                    placeholder="Describe a coding task…  (Ctrl+C cancels running task)",
                    id="prompt",
                )
            with Vertical(id="activity"):
                yield Static(id="side", markup=False)
                yield Vertical(id="cards")
        yield Footer()

    def on_resize(self, event: Any) -> None:
        """窄屏时把活动栏降到主区下方，保留工具卡片可达性。"""
        compact = event.size.width <= 100
        if compact == self._compact_activity:
            return
        self._compact_activity = compact
        body = self.query_one("#body", Horizontal)
        activity = self.query_one("#activity", Vertical)
        if compact:
            body.add_class("compact")
            activity.add_class("compact")
        else:
            body.remove_class("compact")
            activity.remove_class("compact")

    def on_mount(self) -> None:
        self._refresh_sidebar()
        self.query_one("#prompt", Input).focus()
        self.on_resize(type("Resize", (), {"size": self.size})())
        if self.initial_task:
            self.call_after_refresh(self._submit_text, self.initial_task)

    def on_unmount(self) -> None:
        """卸载 TUI 时停止流式 timer，避免残留回调触碰已卸载控件。"""
        self._discard_stream_buffer()

    def _refresh_sidebar(self) -> None:
        side = self.query_one("#side", Static)
        side.update(
            f"{PRODUCT_NAME}\n"
            f"{TAGLINE}\n\n"
            f"{PURPOSE}\n\n"
            f"developer\n{DEVELOPER_NAME}  ·  GitHub: {DEVELOPER_HANDLE}\n\n"
            f"workflow\n{WORKFLOW}\n\n"
            f"workspace\n{self.workspace}\n\n"
            f"session\n{self.session_id}\n\n"
            "controls\n"
            "Enter  send task\n"
            "Ctrl+C  cancel (or copy selection)\n"
            "Ctrl+Shift+C  copy selection\n"
            "Ctrl+L  clear log\n"
            "Ctrl+Q  quit\n\n"
            "commands\n"
            "/help  /session  /sessions\n"
            "/clear  /copy /export /mcp /exit"
        )

    def _submit_text(self, text: str) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.value = text
        self._submit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt":
            self._submit()

    def _submit(self) -> None:
        prompt = self.query_one("#prompt", Input)
        text = prompt.value.strip()
        if not text or self.is_busy:
            return
        prompt.value = ""
        if text.startswith("/"):
            self._command_task = asyncio.create_task(self._run_command(text))
            return
        self._write_user(text)
        self._run_task = asyncio.create_task(self._run_agent(text))

    async def _run_agent(self, text: str) -> None:
        self._set_status("running")
        try:
            self._last_result = await self.agent.run(text)
        except asyncio.CancelledError:
            self.agent.agent.abort()
            self._discard_stream_buffer()
            self._streaming_turn = False
            self._set_status("cancelled")
        except Exception as exc:
            self._flush_pending_stream()
            self._finish_stream_line()
            self._record_error(exc)
            self._set_status("error")
        else:
            self._flush_pending_stream()
            self._finish_stream_line()
            if self._status_text == "running":
                if self._last_result is None:
                    self._set_status("stopped: max_iterations")
                else:
                    self._set_status("idle")
        finally:
            self._run_task = None
            self._stream_events_enabled = False
            self._streaming_turn = False
            self.query_one("#prompt", Input).focus()

    async def _run_command(self, raw: str) -> None:
        try:
            command, _, command_args = raw[1:].partition(" ")
            command = command.strip().lower()
            command_args = command_args.strip()
            if command in {"exit", "quit"}:
                await self.action_quit()
            elif command == "help":
                self._write_system(
                    "/help  show commands\n"
                    "/session [new|ID]  show, create, or restore a session\n"
                    "/sessions  list saved sessions\n"
                    "/clear  reset the current session and visible log\n"
                    "/copy  copy the complete visible conversation\n"
                    "/export  save the conversation under .traceforce/\n"
                    "/mcp  show connected MCP servers\n"
                    "/exit  quit TraceForce"
                )
            elif command == "session":
                if not command_args:
                    self._write_system(
                        f"workspace: {self.workspace}\nsession: {self.session_id}"
                    )
                elif command_args.lower() == "new":
                    await self._switch_session(self.session_store.create())
                else:
                    await self._switch_session(self.session_store.open(command_args))
            elif command == "sessions":
                metas = self.session_store.list()
                if not metas:
                    self._write_system("(no saved sessions)")
                else:
                    self._write_system(
                        "\n".join(
                            f"{meta.id}  ·  {meta.entries} entries  ·  {meta.created_at}"
                            for meta in metas
                        )
                    )
            elif command == "clear":
                self.agent.agent.reset()
                self._clear_view()
                self._write_system("current session cleared")
            elif command == "copy":
                self._copy_transcript()
            elif command in {"export", "save"}:
                self._save_transcript()
            elif command == "mcp":
                await self.agent.agent.ensure_initialized()
                result = self.agent.agent.extension_manager.handle_command("mcp")
                if inspect.isawaitable(result):
                    result = await result
                self._write_system(str(result) if result is not None else "MCP ready")
            else:
                await self.agent.agent.ensure_initialized()
                result = self.agent.agent.extension_manager.handle_command(
                    command, command_args or None
                )
                if inspect.isawaitable(result):
                    result = await result
                self._write_system(str(result) if result is not None else "command complete")
        except (RuntimeError, ValueError) as exc:
            self._record_error(exc)
            self._set_status("error")
        finally:
            self._command_task = None
            if self._status_text == "running command":
                self._set_status("idle")
            self.query_one("#prompt", Input).focus()

    async def _switch_session(self, session: Session) -> None:
        if self.agent_factory is None:
            raise RuntimeError("session switching is unavailable for this app")
        old_agent = self.agent
        await old_agent.agent.extension_manager.close()
        self.agent = self.agent_factory(session)
        self.session_id = session.id
        self._clear_view()
        self._refresh_sidebar()
        self._write_system(f"session switched to {session.id}")
        self._set_status("idle")

    async def request_permission(
        self,
        event: ToolExecutionStart,
        controller: TUIPermissionController,
    ) -> bool:
        """在 Textual 主循环中显示 modal，并异步等待按钮结果。"""
        if self.assume_yes:
            return True
        if self._permission_future is not None:
            return False
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        screen = PermissionDialog(event)
        self._permission_future = future
        self._permission_screen = screen
        controller._future = future
        controller._screen = screen

        def on_dismiss(result: bool | None) -> None:
            if not future.done():
                future.set_result(bool(result))

        self.push_screen(screen, callback=on_dismiss)
        try:
            return await future
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                screen.dismiss(False)
            raise
        finally:
            if self._permission_future is future:
                self._permission_future = None
                self._permission_screen = None
                controller._future = None
                controller._screen = None

    def mark_tool_blocked(self, event: ToolExecutionStart, reason: str) -> None:
        card = self._current_cards.get(event.tool_call_id)
        if card is not None:
            card.block(reason)
        self._set_status("tool blocked")

    def _write_user(self, text: str) -> None:
        self.query_one("#conversation", ConversationLog).append_block(
            "YOU", text, classes="user"
        )

    def _write_system(self, text: str) -> None:
        self.query_one("#conversation", ConversationLog).append_block(
            "SYSTEM", text, classes="system"
        )

    def _record_error(self, exc: Exception) -> None:
        """在界面展示可复制错误，并把诊断保存到本地忽略目录。"""
        message = f"{type(exc).__name__}: {exc}"
        path = self._error_path()
        self._write_system(
            f"[error] {message}\n"
            f"完整错误已保存到 {path}；可使用 Copy output 或 /export。"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"{message}\n\n{traceback.format_exc()}",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _error_path(self) -> Path:
        return self.workspace / ".traceforce" / "tui-error.txt"

    def _copy_transcript(self) -> None:
        self._flush_pending_stream()
        self._finish_stream_line()
        transcript = self.query_one("#conversation", ConversationLog).transcript
        if transcript:
            self.copy_to_clipboard(transcript)
            self._set_status("copied output")
        else:
            self._set_status("no output to copy")

    def _save_transcript(self) -> Path | None:
        self._flush_pending_stream()
        self._finish_stream_line()
        transcript = self.query_one("#conversation", ConversationLog).transcript
        if not transcript:
            self._set_status("no output to save")
            return None
        path = self.workspace / ".traceforce" / "tui-transcript.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(transcript + "\n", encoding="utf-8")
        except OSError as exc:
            self._record_error(exc)
            return None
        self._write_system(f"output saved to {path}")
        self._set_status("output saved")
        return path

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-transcript":
            self._copy_transcript()
        elif event.button.id == "save-transcript":
            self._save_transcript()

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.query_one("#status", Label).update(text)

    def on_tool_card_closed(self, event: ToolCard.Closed) -> None:
        """只关闭可见卡片，不影响已经提交给 runtime 的工具调用。"""
        card = event.card
        self._current_cards.pop(card.tool_call_id, None)
        if card.is_attached:
            card.remove()

    def _copy_focused_selection(self) -> bool:
        """复制当前已有的 TextArea 选区，即使焦点刚回到输入框。"""
        self._flush_pending_stream()
        self._finish_stream_line()
        candidates: list[TextArea] = []
        focused = self.focused
        if isinstance(focused, TextArea):
            candidates.append(focused)
        candidates.extend(
            widget
            for widget in self.query(TextArea)
            if widget is not focused
        )
        for widget in candidates:
            with contextlib.suppress(Exception):
                selected = widget.selected_text
                if selected:
                    self.copy_to_clipboard(selected)
                    self._set_status("copied selection")
                    return True
        return False

    def action_copy_selection(self) -> None:
        """将当前只读文本控件中的选区复制到终端剪贴板。"""
        self._copy_focused_selection()

    def action_cancel_or_copy(self) -> None:
        """有选区时复制，否则保留 Ctrl+C 的取消语义。"""
        if not self._copy_focused_selection():
            self.action_cancel_task()

    def _mark_running_cards_cancelled(self) -> None:
        for card in list(self._current_cards.values()):
            card.cancel()

    def handle_event(self, event: Any) -> None:
        """同步接收 runtime hook 事件并更新 TUI。"""
        if isinstance(event, AgentStart):
            self._stream_events_enabled = True
            self._set_status("starting")
        elif isinstance(event, TurnStart):
            self._streaming_turn = False
            self._turn_had_streamed_text = False
            self._stream_events_enabled = True
            self._write_system(f"TURN {event.iteration}")
        elif isinstance(event, MessageUpdate):
            if not self._stream_events_enabled:
                return
            text = getattr(event.chunk, "content", "") or ""
            if text:
                self._streaming_turn = True
                self._turn_had_streamed_text = True
                self._queue_stream_text(text)
                self._set_status("assistant streaming")
        elif isinstance(event, ToolExecutionStart):
            self._flush_pending_stream()
            self._finish_stream_line()
            card = ToolCard(event)
            self._current_cards[event.tool_call_id] = card
            self._mount_tool_card(card)
            self._set_status(f"running tool: {event.tool_name}")
        elif isinstance(event, ToolExecutionEnd):
            self._flush_pending_stream()
            self._finish_stream_line()
            card = self._current_cards.get(event.tool_call_id)
            if card is not None and card.is_attached:
                card.finish(event)
            self._set_status("tool error" if event.is_error else "tool complete")
        elif isinstance(event, TurnEnd):
            self._flush_pending_stream()
            if event.message.content and not self._turn_had_streamed_text:
                self.query_one("#conversation", ConversationLog).assistant_message(
                    event.message.content
                )
            self._finish_stream_line()
            self._stream_events_enabled = False
        elif isinstance(event, AgentEnd):
            if event.stop_reason == "cancelled":
                self._discard_stream_buffer()
                self._streaming_turn = False
            else:
                self._flush_pending_stream()
                self._finish_stream_line()
            self._stream_events_enabled = False
            self._set_status(f"{event.stop_reason} · {event.iterations} turns")

    def _clear_view(self) -> None:
        self._discard_stream_buffer()
        self._streaming_turn = False
        self._turn_had_streamed_text = False
        self.query_one("#conversation", ConversationLog).clear_transcript()
        self.query_one("#cards", Vertical).remove_children()
        self._current_cards.clear()

    def _queue_stream_text(self, text: str) -> None:
        """以可读的节奏批量刷新 assistant 文本，避免每个 token 抢占画面。"""
        if not text:
            return
        self._stream_buffer += text
        if self._stream_flush_timer is None:
            self._stream_flush_timer = self.set_interval(
                _STREAM_TICK_SECONDS, self._flush_stream_text
            )

    def _flush_stream_text(self) -> None:
        """显示一个节拍的 assistant 文本，保持事件消费非阻塞。"""
        if self._stream_buffer:
            text = self._stream_buffer[:_STREAM_CHARS_PER_TICK]
            self._stream_buffer = self._stream_buffer[len(text):]
            self.query_one("#conversation", ConversationLog).assistant_chunk(text)
        if not self._stream_buffer:
            self._stop_stream_timer()
            if self._finish_stream_after_flush:
                self._finish_stream_after_flush = False
                self._finish_stream_line()

    def _flush_pending_stream(self) -> None:
        """同步显示所有待处理文本，供事件边界和导出操作使用。"""
        if self._stream_buffer:
            self.query_one("#conversation", ConversationLog).assistant_chunk(
                self._stream_buffer
            )
            self._stream_buffer = ""
        self._finish_stream_after_flush = False
        self._stop_stream_timer()

    def _stop_stream_timer(self) -> None:
        timer = self._stream_flush_timer
        self._stream_flush_timer = None
        if timer is not None:
            timer.stop()

    def _discard_stream_buffer(self) -> None:
        """取消或清屏时丢弃尚未显示的文本，避免旧任务回调污染新视图。"""
        self._stream_buffer = ""
        self._finish_stream_after_flush = False
        self._stop_stream_timer()

    def _finish_stream_line(self) -> None:
        if self._stream_buffer:
            self._finish_stream_after_flush = True
            return
        if self._streaming_turn:
            self.query_one("#conversation", ConversationLog).finish_assistant()
            self._streaming_turn = False

    def _mount_tool_card(self, card: ToolCard) -> None:
        """把工具调用作为对话流中的一等卡片插入，而不是堆在输入框上。"""
        self.query_one("#cards", Vertical).mount(card)

    def action_cancel_task(self) -> None:
        """合作式取消当前 Agent 任务，保留已完成的证据卡片。"""
        if self._permission_screen is not None:
            if self.permission_controller is not None:
                self.permission_controller.cancel()
        if self._run_task is None:
            self._discard_stream_buffer()
            self._set_status("idle")
            return
        self._mark_running_cards_cancelled()
        self.agent.agent.abort()
        self._run_task.cancel()
        self._set_status("cancelling")

    def action_clear_log(self) -> None:
        """清空可见日志，不删除 Session 历史。"""
        self._clear_view()
        self._set_status("idle")

    async def action_quit(self) -> None:
        """取消任务、关闭当前扩展资源并退出应用。"""
        if self.permission_controller is not None:
            self.permission_controller.cancel()
        self._discard_stream_buffer()
        task = self._run_task
        if task is not None:
            self._mark_running_cards_cancelled()
            self.agent.agent.abort()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        command_task = self._command_task
        if command_task is not None and command_task is not asyncio.current_task():
            command_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await command_task
        with contextlib.suppress(Exception):
            await self.agent.agent.extension_manager.close()
        self.exit()


class TUIHook:
    """将 runtime hook 回调转发到 Textual 当前事件循环。"""

    def __init__(self, app: TraceForceApp) -> None:
        self.app = app

    def __call__(self, event: Any) -> None:
        # Agent task 与 Textual App 在同一个 asyncio loop；直接调用避免 call_from_thread
        # 在同线程时报错，也保证 ToolExecutionStart 卡片先于权限 modal 创建。
        self.app.handle_event(event)


def build_tui_app(args: Any) -> TraceForceApp:
    """按 CLI 参数装配 TUI，复用纯终端模式的模型、workspace 和 Session 边界。"""
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"Workspace is not a directory: {workspace}")

    from dotenv import load_dotenv

    load_dotenv(workspace / ".env")
    args.workspace = workspace
    llm = build_llm(args)
    store = SessionStore(workspace=workspace)
    session = store.open(args.session) if args.session else store.create()
    instructions = load_project_instructions(workspace)
    system_prompt = DEFAULT_SYSTEM_PROMPT
    if instructions:
        system_prompt += f"\n\n{instructions}"

    permission = TUIPermissionController()
    holder: dict[str, TraceForceApp] = {}

    def dispatch(event: Any) -> None:
        app = holder.get("app")
        if app is not None:
            app.handle_event(event)

    def make_agent(target_session: Session) -> CodingAgent:
        return CodingAgent(
            workspace=workspace,
            llm=llm,
            session=target_session,
            system_prompt=system_prompt,
            max_iterations=args.max_iterations,
            extension_dirs=[
                workspace / ".agents" / "extensions",
                Path(__file__).with_name("mcp.py"),
            ],
            hooks=[
                (AgentStart, dispatch),
                (TurnStart, dispatch),
                (MessageUpdate, dispatch),
                (ToolExecutionStart, dispatch),
                (ToolExecutionStart, permission),
                (ToolExecutionEnd, dispatch),
                (TurnEnd, dispatch),
                (AgentEnd, dispatch),
            ],
        )

    agent = make_agent(session)
    app = TraceForceApp(
        agent=agent,
        workspace=workspace,
        session_id=session.id,
        session_store=store,
        assume_yes=args.assume_yes,
        task=args.prompt,
        agent_factory=make_agent,
        permission_controller=permission,
    )
    permission.bind(app)
    holder["app"] = app
    return app


def run_tui(args: Any) -> None:
    """同步运行 Textual 应用，并确保扩展资源在退出时关闭。"""
    app = build_tui_app(args)
    try:
        app.run()
    finally:
        with contextlib.suppress(Exception):
            asyncio.run(app.agent.agent.extension_manager.close())


def _permission_description(event: ToolExecutionStart) -> str:
    args = event.args
    if event.tool_name == "bash":
        return f"bash\n{args.get('command', '')}"
    if event.tool_name == "write":
        content = str(args.get("content", ""))
        preview = content[:1200]
        suffix = "..." if len(content) > 1200 else ""
        return f"write {args.get('path', '')} ({len(content)} chars)\n{preview}{suffix}"
    old_text = str(args.get("old_text", ""))
    new_text = str(args.get("new_text", ""))
    return (
        f"edit {args.get('path', '')}\n"
        f"replace {len(old_text)} chars with {len(new_text)} chars"
    )


def _format_args(args: dict[str, Any]) -> str:
    try:
        return json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(args)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n… <{len(text) - limit} chars clipped>"
