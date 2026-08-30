"""产品层薄装配：文件工具工厂 + CodingAgent（框架 Agent + 文件工具自动装配）。"""

from __future__ import annotations

from pathlib import Path

from traceforce_runtime import Agent  # pyright: ignore[reportMissingImports]
from traceforce_runtime.tools import Tool  # pyright: ignore[reportMissingImports]

from traceforce.mutation_queue import FileMutationQueue
from traceforce.tools import (
    make_bash_tool,
    make_edit_tool,
    make_read_tool,
    make_write_tool,
)


def build_coding_tools(workspace: str | Path) -> list[Tool]:
    """返回 4 个文件工具，共享 workspace 内的单文件变更队列。"""
    workspace = Path(workspace).resolve()
    mutation_queue = FileMutationQueue()
    return [
        make_read_tool(workspace),
        make_write_tool(workspace, mutation_queue=mutation_queue),
        make_edit_tool(workspace, mutation_queue=mutation_queue),
        make_bash_tool(workspace),
    ]


class CodingAgent:
    """产品层：框架 Agent + 文件工具自动装配（薄封装）。"""

    def __init__(
        self,
        *,
        workspace: str | Path,
        llm,
        session,
        system_prompt: str | None = None,
        extra_tools: list | tuple = (),
        **kw,
    ):
        tools = build_coding_tools(workspace) + list(extra_tools)
        self.agent = Agent(
            llm=llm, tools=tools, session=session, system_prompt=system_prompt, **kw
        )

    async def run(self, user_input: str):
        return await self.agent.run(user_input)
