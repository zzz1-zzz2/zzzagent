"""产品层装配离线测试：build_coding_tools + CodingAgent 自动装配。"""

import pytest
from traceforce_llm import Response

from traceforce_runtime import Agent
from traceforce_runtime.session import Session
from traceforce.agent import CodingAgent, build_coding_tools


class _FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    async def achat_stream(self, *, messages, tools=None, **kwargs):
        yield self.responses.pop(0)

    async def achat(self, *, messages, tools=None, **kwargs):
        return self.responses.pop(0)

    def chat(self, *, messages, tools=None, **kwargs):
        return self.responses.pop(0)


def test_build_coding_tools_returns_four(tmp_path):
    tools = build_coding_tools(tmp_path)
    names = sorted(t.name for t in tools)
    assert names == ["bash", "edit", "read", "write"]


def test_coding_agent_auto_registers_file_tools(tmp_path):
    session = Session(path=tmp_path / "s.jsonl")
    agent = CodingAgent(workspace=tmp_path, llm=_FakeLLM([]), session=session)
    names = {t.name for t in agent.agent.registry.list()}
    assert {"read", "write", "edit", "bash"} <= names


def test_coding_agent_shares_file_mutation_queue(tmp_path):
    """产品层 write/edit 共享一个文件变更队列。"""
    session = Session(path=tmp_path / "s.jsonl")
    agent = CodingAgent(workspace=tmp_path, llm=_FakeLLM([]), session=session)
    write = agent.agent.registry.get("write")
    edit = agent.agent.registry.get("edit")
    assert write is not None and edit is not None
    assert write.func.__closure__ is not None
    assert edit.func.__closure__ is not None
    write_queue = next(
        cell.cell_contents
        for cell in write.func.__closure__
        if isinstance(cell.cell_contents, object)
        and cell.cell_contents.__class__.__name__ == "FileMutationQueue"
    )
    edit_queue = next(
        cell.cell_contents
        for cell in edit.func.__closure__
        if isinstance(cell.cell_contents, object)
        and cell.cell_contents.__class__.__name__ == "FileMutationQueue"
    )
    assert write_queue is edit_queue


def test_coding_agent_merges_extra_tools(tmp_path):
    from traceforce_runtime import tool

    @tool
    def double(x: int) -> int:
        """Double x."""
        return x * 2

    session = Session(path=tmp_path / "s.jsonl")
    agent = CodingAgent(
        workspace=tmp_path, llm=_FakeLLM([]), session=session, extra_tools=[double]
    )
    names = {t.name for t in agent.agent.registry.list()}
    assert {"read", "write", "edit", "bash", "double"} <= names


@pytest.mark.anyio
async def test_coding_agent_run_delegates(tmp_path):
    session = Session(path=tmp_path / "s.jsonl")
    agent = CodingAgent(workspace=tmp_path, llm=_FakeLLM([Response(content="hi", model="fake")]), session=session)
    result = await agent.run("hello")
    assert result == "hi"