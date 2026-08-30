# traceforce-runtime

`traceforce-runtime` 是 TraceForce 的通用异步 Agent 运行时。它不依赖终端界面，也不内置 Coding Agent 的文件工具；产品层通过明确的工具和事件接口将它装配到具体工作区。

## 能力边界

- 原生 `asyncio` ReAct 循环和流式模型响应；
- `Tool`、`@tool`、Pydantic 参数 Schema 和 `ToolResult` 错误反馈；
- 只读工具批量并发，写操作按调用顺序执行并保序回填；
- Agent、Turn、模型消息、工具执行和上下文生命周期事件；
- JSONL 树状 Session，支持恢复、回退和分叉；
- 上下文裁切、工具结果压缩、大结果落盘和摘要缓存；
- Skills、Subagents、Tasks、Extensions、Plugins、Memory 和 steering/follow-up 队列。

运行时只负责状态、循环、工具契约和生命周期，不决定 CLI 输出格式、终端 UI 或具体 workspace 权限策略。

## 最小示例

```python
import asyncio
from pathlib import Path

from traceforce_llm import Config, LLM
from traceforce_runtime.agent import Agent
from traceforce_runtime.session import Session
from traceforce_runtime.tools import tool


@tool(is_parallel_safe=True)
def count_lines(text: str) -> int:
    """Count lines in text."""
    return len(text.splitlines())


async def main() -> None:
    session = Session(path=Path("session.jsonl"))
    llm = LLM(config=Config(provider="openai", model="your-model-name"))
    agent = Agent(
        llm=llm,
        tools=[count_lines],
        session=session,
        system_prompt="Use tools when they provide reliable evidence.",
    )
    print(await agent.run("Count the lines in this sample: a\\nb"))


if __name__ == "__main__":
    asyncio.run(main())
```

API key 应通过环境变量或未入库的配置文件提供，不要写进源码、示例、日志或文档。

## 运行测试

```bash
cd packages/traceforce-runtime
uv sync
uv lock --check
uv run python -m pytest -q
```

测试使用离线 FakeLLM，不要求网络或真实凭据。产品层的 CLI、workspace 文件工具和 MCP 集成请使用 `packages/traceforce`。

## 包结构

```text
src/traceforce_runtime/
├── agent.py             # Agent 状态、循环与生命周期编排
├── tools/               # Tool、ToolResult、装饰器和 task 工具
├── registry.py          # Schema 注册、批量执行和顺序回填
├── events.py            # 生命周期事件、HookResult 和 HookRegistry
├── session.py           # SessionEntry、SessionTree 和 JSONL 持久化
├── session_store.py     # workspace 内的会话仓库
├── context.py           # 上下文视图压缩与摘要缓存
├── skills.py            # SKILL.md 发现和渐进式加载
├── subagents.py         # 声明式子代理定义
├── tasks.py             # 子任务生命周期与隔离执行
├── extensions/          # Python 扩展 API 和命令路由
├── plugins.py           # 可选资源包发现与拆分
├── memory.py            # 长期记忆和冻结快照
└── message_queue.py     # steering / follow-up 队列
```

## 设计不变式

1. 工具失败反馈给模型，不让局部异常摧毁主循环；
2. 持久化使用临时文件、`fsync` 和原子替换；
3. 上下文压缩只生成模型视图，不删除真实历史；
4. 流式取消时不写入不完整 assistant 消息；
5. 子代理使用独立 Session，并禁用递归委派和共享记忆；
6. 运行时不假定 CLI、终端 UI 或具体文件系统工具存在。
