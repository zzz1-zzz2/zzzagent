"""子代理委派的任务生命周期：Task 模型、状态和隔离执行。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from traceforce_runtime.session import Session
from traceforce_runtime.subagents import DEFAULT_SUBAGENT, Subagent, SubagentManager

if TYPE_CHECKING:
    from traceforce_runtime.agent import Agent


class TaskStatus(StrEnum):
    """委派任务三态。"""

    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class Task:
    """一次委派任务：有 id、状态、结果，可查询。"""

    id: str
    status: TaskStatus
    result: str | None = None
    error: str | None = None

    def set_result(self, result: str) -> None:
        """标记成功。"""
        self.result = result
        self.error = None
        self.status = TaskStatus.COMPLETED

    def set_error(self, error: str) -> None:
        """标记失败。"""
        self.error = error
        self.result = None
        self.status = TaskStatus.ERROR


def _system_for(sub: Subagent, parent: Agent) -> str:
    """组合子代理正文和明确指定的技能清单。"""
    parts = [sub.content]
    if sub.skills:
        block = parent.skill_manager.format_prompt(sub.skills)
        if block:
            parts.append(block)
    return "\n\n".join(p for p in parts if p)


def _filter_tools(parent: Agent, sub: Subagent) -> list:
    """按子代理白名单和黑名单过滤父工具，排除 task 与 memory。"""
    tools = [t for t in parent.registry.list() if t.name not in ("task", "memory")]
    if sub.tools is not None:
        allowed = set(sub.tools)
        tools = [t for t in tools if t.name in allowed]
    black = set(sub.disallowed_tools)
    return [t for t in tools if t.name not in black]


class TaskManager:
    """委派任务的生命周期管理器。"""

    def __init__(self, manager: SubagentManager, parent: Agent):
        self._manager = manager
        self._parent = parent
        self._counter = 0
        self._active_agents: dict[str, Agent] = {}

    def steer_task(self, task_id: str, message: str) -> bool:
        """向指定运行中的子代理发送即时转向。"""
        agent = self._active_agents.get(task_id)
        if agent is not None:
            agent.steer(message)
            return True
        return False

    def follow_up_task(self, task_id: str, message: str) -> bool:
        """向指定运行中的子代理追加后续消息。"""
        agent = self._active_agents.get(task_id)
        if agent is not None:
            agent.follow_up(message)
            return True
        return False

    async def start_task(self, prompt: str, subagent_type: str = "default") -> Task:
        """创建任务、运行子代理并更新最终状态。"""
        task = self._create_task(subagent_type)
        try:
            task.set_result(await self._run(prompt, subagent_type, task.id))
        except Exception as exc:
            task.set_error(str(exc))
        return task

    def _create_task(self, subagent_type: str) -> Task:
        self._counter += 1
        return Task(id=f"task_{self._counter:08x}", status=TaskStatus.RUNNING)

    async def _run(self, prompt: str, subagent_type: str, task_id: str) -> str:
        """创建隔离 Session 和子代理，执行任务后返回总结。"""
        from traceforce_runtime.agent import Agent

        sub = self._manager.get(subagent_type)
        if sub is None and subagent_type == "default":
            sub = DEFAULT_SUBAGENT
        if sub is None:
            available = ", ".join(sorted(self._manager.subagents)) or "(none)"
            raise ValueError(
                f"Unknown subagent '{subagent_type}'. Available: {available}"
            )
        child_session = Session(
            path=self._parent.session.path.parent / "subagents" / f"agent-{task_id}.jsonl",
            cwd=self._parent.session.cwd,
            metadata={
                "agent_type": subagent_type,
                "parent_session_id": self._parent.session.id,
            },
        )
        child_session.save()
        child = Agent(
            llm=self._parent.llm,
            tools=_filter_tools(self._parent, sub),
            session=child_session,
            system_prompt=_system_for(sub, self._parent),
            model=sub.model,
            max_iterations=(
                sub.max_turns
                if sub.max_turns is not None
                else self._parent.max_iterations
            ),
            skill_dirs=[],
            subagent_dirs=[],
            memory_dir=False,
            plugin_dirs=[],
        )
        self._active_agents[task_id] = child
        try:
            return (await child.run(prompt)) or "(no summary)"
        except Exception as exc:
            raise RuntimeError(f"Subagent '{subagent_type}' failed: {exc}") from exc
        finally:
            self._active_agents.pop(task_id, None)
