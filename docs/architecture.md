# 架构说明

> TraceForce 的核心边界是 **Product → Runtime → LLM**；`evals/` 位于运行时之外，负责独立验收。

## 1. 分层关系

```text
┌──────────────────────────────────────────────────────────────┐
│ Product: traceforce                                         │
│ CLI · REPL · TUI · CodingAgent · coding tools · permissions  │
│ workspace · project instructions · MCP                      │
└──────────────────────────────┬───────────────────────────────┘
                               │ 装配
┌──────────────────────────────▼───────────────────────────────┐
│ Runtime: traceforce-runtime                                 │
│ Agent loop · Tool · Registry · Hooks · Context · Session     │
│ Skills · Subagents · Tasks · Extensions · Plugins · Memory   │
└──────────────────────────────┬───────────────────────────────┘
                               │ 统一协议
┌──────────────────────────────▼───────────────────────────────┐
│ LLM: traceforce-llm                                         │
│ Provider adapters · Message · Response · StreamChunk         │
│ streaming tool-call aggregation                              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Evals: independent acceptance layer                         │
│ task.md · setup.sh · verify.sh · optional evidence           │
└──────────────────────────────────────────────────────────────┘
```

分层的目的不是把代码拆成名字不同的目录，而是让每层有可检查的责任：

- 产品层知道 workspace 和用户交互，但不复制 Agent loop；
- 运行时知道模型协议和工具契约，但不知道自己是不是 Coding Agent；
- LLM 层知道 Provider 差异，但不读取文件、不执行命令；
- evals 知道如何准备任务和做独立判断，但不参与产品运行时。

## 2. Agent loop

`traceforce-runtime` 的 `Agent` 以原生 `asyncio` 实现多轮工具调用：

```text
UserInput
  → AgentStart
  → ContextManager.prepare()
  → LLM.achat_stream()
  → MessageUpdate
  → 聚合 tool_calls
  → ToolExecutionStart / 权限 Hook
  → ToolRegistry.execute_batch()
  → ToolExecutionEnd
  → ToolResult 写回消息
  → 下一轮模型调用
  → 无 tool call 时 AgentEnd
```

每轮模型输出会先转换为统一的 `Response` / `StreamChunk` 数据结构。工具参数由 Pydantic schema 校验；执行成功或失败都形成 `ToolResult`。失败结果会写入 `tool` 消息，让模型能够根据实际错误继续修复。

### 终止条件

- **语义终止**：模型不再请求工具，返回最终文本；
- **资源终止**：产品默认 `max_iterations=30`，避免模型持续调用工具；
- **合作式取消**：宿主调用 `Agent.abort()`，在安全点停止当前运行并丢弃未完成的流式 assistant 消息。

高级调用方可以显式传入 `max_iterations=None`，但产品 CLI 保留默认上限。

## 3. 工具执行和并发

运行时 `Tool` 将 Python 函数、参数 schema、超时和并发属性封装为统一契约。`ToolRegistry` 根据工具是否标记为并行安全来批量执行：只读工具可以并发，写操作按照调用顺序执行并保序回填。

产品层的四个内置工具位于 [`packages/traceforce/src/traceforce/tools.py`](../packages/traceforce/src/traceforce/tools.py)：

- `read`：只读并限制在 workspace 内；
- `write`：创建或覆盖文件，使用变更队列；
- `edit`：要求旧文本唯一匹配后替换；
- `bash`：在 workspace 根目录运行非交互 shell 命令。

## 4. 事件和产品 UI

runtime 通过生命周期事件暴露状态，而不是直接依赖终端：

- Agent：`AgentStart`、`AgentEnd`；
- Turn：`TurnStart`、`TurnEnd`；
- 消息：`MessageStart`、`MessageUpdate`、`MessageEnd`；
- 工具：`ToolExecutionStart`、`ToolExecutionUpdate`、`ToolExecutionEnd`；
- 上下文：`BeforeModelCall`、`ContextCompacted`。

纯终端 `TerminalPresenter` 和 Textual TUI 都是事件消费者。TUI 的 ToolCard、权限弹窗和状态栏不改变 runtime 的决策逻辑；关闭卡片只隐藏 UI，不取消已经提交的工具调用。

## 5. Session 与 Context

Session 以 workspace 下的 JSONL 文件保存消息树。每条 entry 有 ID 和父子关系，因此可以恢复当前路径、回退到旧节点或从某个节点分叉。`SessionStore` 只负责创建、发现和打开会话；Agent 负责把本轮消息写回 Session。

ContextManager 在每次模型调用前生成上下文视图：

- 真实历史保留在 Session；
- 发送给模型的内容可以按 token 预算裁切；
- 大型工具结果可独立落盘并用摘要替代；
- 压缩只改变模型视图，不删除真实记录。

## 6. 安全边界

TraceForce 的安全策略是产品层和 runtime 工具契约的一部分，不依赖模型自觉：

- 文件路径 `resolve()` 后必须位于 workspace 根目录；
- 写操作和可执行命令默认需要权限确认；
- `--yes` 只跳过确认，不关闭路径检查、危险命令过滤和超时；
- bash 使用 EOF stdin、非交互环境变量和 120 秒超时；
- Unix 上对超时/取消尝试按进程组清理；
- `.env`、Session、MCP 配置和 workspace 外部文件不应被写入凭据。

内置 bash **不是操作系统级沙箱**。它不提供完整 PTY，无法保证所有同步第三方程序、通过 `/dev/tty` 绕过 stdin 的程序或 Windows 进程树都能立即结束。MCP server 可以执行本地高权限程序，因此应作为独立信任边界审查。

## 7. 为什么 evals 不放进 runtime

评测任务需要能够在 Agent 之外独立判断结果。如果 verifier 复用 Agent 的状态或最后总结，就无法回答“实现是否真的完成”。因此 `evals/` 只提供：

1. `setup.sh`：恢复固定初始状态或空 workspace；
2. `task.md`：给 Agent 的任务描述，不泄露答案；
3. `verify.sh`：独立 PASS/FAIL 裁判；
4. 可选脱敏证据：测试输出、patch、summary 或人工 UI 记录。

完整协议见 [评测指南](evaluation.md)。
