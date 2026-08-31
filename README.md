# TraceForce Coding Agent

> 面向真实软件工程任务的可验证编程智能体
>
> **由 zzz 开发** · GitHub：[zzz1-zzz2/zzzagent](https://github.com/zzz1-zzz2/zzzagent)

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-309%20passed-2ea44f)](#测试与验收)
[![Status](https://img.shields.io/badge/status-development-orange)](#当前范围)

TraceForce 是由 **zzz** 开发的、可以实际读取项目、修改文件、执行检查并根据结果继续修复的 Coding Agent。它不是只返回建议的聊天窗口，也不依赖现成 Agent 编排框架或 Agent SDK；模型适配、工具调用循环、上下文视图、Session、权限和产品交互都在本仓库中实现。

```text
用户任务
  ↓
读取项目 → 分析问题 → 修改文件 → 运行测试/构建 → 根据错误继续修复 → 汇报证据
```

本 README 先说明产品如何工作，再给出运行、测试和评测入口。实现细节按职责分布在 [packages/](packages/)；复现任务在 [evals/](evals/)；文档索引在 [docs/README.md](docs/README.md)。

---

## 一眼看懂

### TraceForce 解决什么问题？

很多模型应用只能生成代码片段，无法可靠地完成“读代码—改代码—跑验证—处理失败”这一闭环。TraceForce 将这个闭环拆成可观察的控制流：

1. **Inspect**：读取项目文件、项目说明和已有实现；
2. **Plan**：根据真实文件内容选择最小修改路径；
3. **Change**：通过受保护的 `write` / `edit` 工具变更文件；
4. **Verify**：通过 `bash` 运行测试、构建或静态检查；
5. **Recover**：把工具错误反馈给模型，允许下一轮修复；
6. **Explain**：汇报实际修改、验证结果和仍存在的风险。

模型的最终文字不是唯一裁判。对可复现评测，`evals/` 使用独立 verifier 检查工作区状态。

### 四个内置 Coding 工具

| 工具 | 职责 | 默认策略 |
| --- | --- | --- |
| `read` | 分页读取 workspace 内的文件 | 自动允许 |
| `write` | 创建或覆盖文件 | 执行前确认 |
| `edit` | 对唯一匹配文本做精确替换 | 执行前确认 |
| `bash` | 在 workspace 根目录执行测试、构建和检查命令 | 执行前确认 |

每个工具都经过参数校验并返回结构化 `ToolResult`。工具失败不会悄悄丢失：错误会写回模型上下文，推动下一轮决策。

---

## 架构：Product → Runtime → LLM

```text
┌─────────────────────────────────────────────────────────────┐
│ TraceForce Product                                          │
│ CodingAgent · CLI · REPL · Textual TUI · read/write/edit/   │
│ bash · workspace 边界 · 权限确认 · 项目说明 · MCP           │
└──────────────────────────────┬──────────────────────────────┘
                               │ 装配工具、Session 和 hooks
┌──────────────────────────────▼──────────────────────────────┐
│ traceforce-runtime                                          │
│ 原生 asyncio Agent loop · Tool/Registry · ToolResult        │
│ 生命周期事件 · Context · JSONL Session · 扩展机制           │
└──────────────────────────────┬──────────────────────────────┘
                               │ 调用统一模型协议
┌──────────────────────────────▼──────────────────────────────┐
│ traceforce-llm                                              │
│ Message · Response · StreamChunk · tool-call 聚合           │
│ OpenAI · DeepSeek · Anthropic · OpenAI-compatible gateway    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ evals（独立验收层，不参与产品运行时）                       │
│ task.md · setup.sh · verify.sh · 可选脱敏结果证据            │
└─────────────────────────────────────────────────────────────┘
```

### `traceforce-llm`：模型边界

只负责模型服务连接和协议归一化：

- OpenAI、DeepSeek、Anthropic 和 OpenAI 兼容网关适配；
- 同步、异步和流式调用接口；
- 统一 `Message`、`Response`、`StreamChunk`；
- 聚合流式 tool-call 分片；
- 统一 usage、finish reason 和 reasoning 元数据。

它不知道 workspace、文件工具或产品 UI，也不实现 Agent loop。详见 [`packages/traceforce-llm/README.md`](packages/traceforce-llm/README.md)。

### `traceforce-runtime`：通用运行时

负责状态和控制流，而不是具体产品：

- 原生 `asyncio` ReAct 循环；
- `Tool`、Pydantic 参数 Schema、批量执行和 `ToolResult`；
- 只读工具并发，写工具串行并按调用顺序回填；
- Agent、Turn、消息、工具和上下文生命周期事件；
- JSONL 树状 Session、恢复、回退、分叉和上下文压缩；
- Skills、Subagents、Tasks、Extensions、Plugins、Memory 和 steering/follow-up 队列。

它不决定终端输出格式、TUI 布局或具体 workspace 权限策略。详见 [`packages/traceforce-runtime/README.md`](packages/traceforce-runtime/README.md)。

### `traceforce`：面向开发者的产品层

负责将通用 runtime 装配成可用 Coding Agent：

- `traceforce` console script、一次性任务和交互式 REPL；
- Textual 全屏 TUI（`--tui`）；
- workspace 内的 `read`、`write`、`edit`、`bash`；
- 权限确认、危险命令过滤、超时和取消；
- `AGENTS.md` / `CLAUDE.md` 项目说明加载；
- MCP stdio 客户端和 `/mcp` 状态命令；
- Session 创建、列表和恢复。

详见 [`packages/traceforce/README.md`](packages/traceforce/README.md)。

---

## 快速开始

### 1. 环境要求

运行 TraceForce 本身需要：

- Python 3.11+；
- [uv](https://docs.astral.sh/uv/)；
- 一个兼容的模型 API。

运行完整 `evals/` 还需要：

- Git 和可访问 GitHub 的网络环境；
- Node.js、npm 和可访问 npm registry 的网络环境；
- Chrome、Firefox 或其他浏览器，用于任务 03 的人工 UI 验收。

setup 脚本会把任务专用 Python 依赖安装到 workspace 内的 `.eval-venv`，不会安装或修改宿主机的 Python、Node.js、npm 和系统包。TraceForce 能创建和配置项目级环境，但不负责配置操作系统。

### 2. 安装三个独立包

```bash
cd packages/traceforce-llm
uv sync

cd ../traceforce-runtime
uv sync

cd ../traceforce
uv sync
```

开发时直接在 `packages/traceforce` 目录使用 `uv run` 即可。

### 3. 配置模型

将模板复制到目标项目的 workspace 根目录，并只在本地填写配置：

```bash
cp packages/traceforce/.env.example /path/to/your-project/.env
```

最小配置示例：

```dotenv
TRACEFORCE_PROVIDER=openai
TRACEFORCE_MODEL=your-model-name
OPENAI_API_KEY=
```

也可以使用 Provider 专用变量：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=your-model-name
```

API key 只允许来自环境变量或未入库的本地配置文件。TraceForce 不接受命令行明文 key，也不会把 key 打印到终端。请不要把真实凭据写入仓库、README、Session、patch、截图、视频或最终压缩包。

### 4. 启动

在仓库中运行一个一次性任务：

```bash
uv run --project packages/traceforce traceforce \
  --workspace /path/to/your-project \
  "读取项目，定位失败测试的原因，修改最小必要代码并运行测试验证"
```

省略任务文本可进入交互式 REPL：

```bash
uv run --project packages/traceforce traceforce \
  --workspace /path/to/your-project
```

信任 workspace 且希望跳过写操作确认时才使用 `--yes`：

```bash
uv run --project packages/traceforce traceforce \
  --workspace /path/to/your-project \
  --yes \
  "运行测试并修复失败"
```

`--yes` 只跳过 `bash`、`write`、`edit` 的人工确认，不会关闭 workspace 路径检查、危险命令过滤或超时保护。

### 5. 启动 Textual TUI

```bash
uv run --project packages/traceforce traceforce \
  --workspace /path/to/your-project \
  --tui
```

TUI 提供：

- workspace、Session 和 Agent 状态展示；
- assistant 流式输出；
- 可选中复制的对话和工具详情；
- 可折叠、可复制、可关闭的工具卡片；
- Allow/Deny 异步权限弹窗；
- `/help`、`/session`、`/sessions`、`/clear`、`/mcp`、`/exit`；
- Ctrl+C 取消当前任务，Ctrl+Shift+C 复制选区，Ctrl+L 清除可见日志，Ctrl+Q 退出。

已完成的工具卡片默认折叠；关闭只影响可见 UI，不取消底层工具调用。剪贴板能力取决于终端的 OSC52 支持。

---

## 运行时行为与安全边界

### Agent loop

TraceForce 自己实现了以下循环，不把控制流交给 Agent 编排框架：

```text
UserInput
  → AgentStart
  → ContextManager.prepare()
  → LLM streaming
  → MessageUpdate
  → 解析 tool_calls
  → 权限 Hook
  → ToolRegistry.execute_batch()
  → ToolResult 写回消息
  → 下一轮模型调用
  → 没有 tool call 时结束
  → AgentEnd
```

循环有两个终止条件：

- 模型不再请求工具时自然结束；
- 默认最多 30 次迭代，防止异常模型持续调用工具。

高级调用方可以显式传入 `max_iterations=None` 禁用资源上限，但产品 CLI 默认保留 30 次限制。用户按 Ctrl+C 时使用合作式取消；正在运行的第三方同步程序不保证立即终止。

### Workspace contract

- 所有文件路径解析后必须位于 workspace 根目录；
- `../`、越界绝对路径和符号链接越界访问会被拒绝；
- `bash` 的 cwd 是 workspace，stdin 使用 EOF，不继承 TUI 输入；
- 内置 bash 设置常见非交互环境变量，并有 120 秒超时；
- Unix 上按进程组尽力清理超时或取消的子进程；
- 文件写入和精确编辑使用 workspace 内的单文件变更队列。

bash **不是操作系统级沙箱**。当前版本不提供完整 PTY，也不能保证所有第三方同步工具、通过 `/dev/tty` 绕过 stdin 的程序或 Windows 进程树都能立即终止。MCP server 同样可以执行本地高权限程序，只加载你信任的 `.mcp.json`。

### Session

Session 默认保存在目标 workspace 的 `.traceforce/sessions/`：

- JSONL 记录消息和父子关系；
- 支持恢复、回退和分叉；
- 大型工具结果可以独立落盘；
- 上下文压缩只改变发送给模型的视图，不删除真实历史；
- 取消时不会把不完整的 assistant 流写入会话。

REPL 内置命令：

```text
/help       显示帮助
/session    显示当前 workspace 和 Session ID
/sessions   列出已保存 Session
/clear      清空当前会话并保留配置
/exit       退出
```

---

## MCP 扩展

在目标 workspace 根目录创建未入库的 `.mcp.json`：

```json
{
  "mcpServers": {
    "local-tools": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"],
      "env": {}
    }
  }
}
```

TraceForce 会通过异步 stdio 连接 MCP server，将远程工具转换为 runtime `Tool`，并在 `/mcp` 中显示连接状态。MCP 配置和 server 属于独立的高权限信任边界；不要在不信任的 workspace 中加载它们。

---

## 可复现评测：`evals/`

`evals/` 只负责定义“如何证明实现有效”，不复制 Agent loop、工具实现或 Session。每个任务遵循：

```text
Prepare → Initial verification → Run TraceForce → Final verification → Collect Evidence → Reset
```

| 任务 | 工程能力 | 独立 verifier |
| --- | --- | --- |
| [01 — tqdm bugfix](evals/tasks/01-tqdm-bugfix/) | 阅读现有 Python 仓库并修复简单 API 回归 | 定向测试 + 独立行为断言 |
| [02 — Sanic bugfix](evals/tasks/02-sanic-bugfix/) | 推理 Blueprint middleware 注册顺序 | 独立 registry 顺序检查 |
| [03 — DevBoard greenfield](evals/tasks/03-devboard-greenfield/) | 从空目录配置 React + Vite 并完成生产构建 | `package.json`、build script、`npm run build` + 人工 UI 验收 |

### Before TraceForce / After TraceForce

| 任务 | Before TraceForce | After TraceForce |
| --- | --- | --- |
| 任务 01 tqdm | buggy revision；目标行为检查失败 | 目标行为恢复；独立 verifier 通过 |
| 任务 02 Sanic | middleware 顺序错误；独立检查失败 | middleware 顺序正确；独立 verifier 通过 |
| 任务 03 DevBoard | 空 workspace；`package.json` 不存在 | React + Vite 项目生成；production build 通过，另做人工 UI 验收 |

这里的初始状态检查不是和其他 Agent 或模型比较的 benchmark baseline，而是确认同一个任务在 TraceForce 介入前后的状态变化。这个项目只有一个被测 Agent：TraceForce。

开始评测前，必须先做 TraceForce 介入前的初始状态检查；TraceForce 的最后总结不能替代独立 verifier。具体协议和证据要求见 [`evals/README.md`](evals/README.md) 与 [`docs/evaluation.md`](docs/evaluation.md)。

---

## 测试与验收

三个包都支持锁文件检查、离线测试和 wheel 构建：

```bash
for package in traceforce-llm traceforce-runtime traceforce; do
  (cd "packages/$package" && uv lock --check && uv run python -m pytest -q && uv build)
done
```

当前记录的离线测试数量：

- `traceforce-llm`：36 项；
- `traceforce-runtime`：228 项；
- `traceforce`：45 项；
- 合计：309 项。

测试使用 FakeLLM、Fake SDK、本地假 MCP server 和临时 workspace，不需要网络或真实 API key。测试覆盖 Provider 归一化、流式 tool-call 聚合、Agent loop、Tool Schema、错误反馈、Hook、Session、Context、扩展、文件工具、MCP、CLI 和 TUI。

测试通过不等于已经完成真实 API E2E、浏览器人工验收或发布流程；这些证据需要单独记录，不能从离线测试统计推导出来。

---

## 文档地图

| 文档 | 用途 |
| --- | --- |
| [README.md](README.md) | 产品定位、快速开始、架构和能力边界 |
| [README.txt](README.txt) | 适合纯文本环境的同步入口 |
| [docs/README.md](docs/README.md) | 文档导航和推荐阅读顺序 |
| [docs/architecture.md](docs/architecture.md) | 模块职责、Agent loop、事件和数据边界 |
| [docs/development.md](docs/development.md) | 本地开发、测试、构建和故障排查 |
| [docs/evaluation.md](docs/evaluation.md) | 评测协议、任务证据和复现要求 |
| [docs/demo.md](docs/demo.md) | 推免答辩和现场演示的诚实操作脚本 |
| [ROADMAP.md](ROADMAP.md) | 只记录尚未交付的后续能力 |

---

## 当前范围

当前版本已经提供：

- 可运行的终端 Coding Agent、REPL 和 Textual TUI；
- 原生异步 Agent loop、工具注册、错误反馈和生命周期事件；
- OpenAI、DeepSeek、Anthropic 和 OpenAI 兼容网关适配；
- workspace 边界、权限确认、非交互 bash、超时和 Unix 进程组尽力清理；
- JSONL Session、Context、Skills、Subagents、Tasks、Extensions、Plugins、Memory 和 MCP；
- 三个可复现评测任务及独立 verifier。

以下能力仍在路线图中，不能视为当前版本已经实现：

- typed trajectory；
- WorkspaceChangeTracker 和独立 evidence 数据模型；
- `traceforce check`；
- 完整交互式 PTY 终端转发；
- 任意第三方同步工具的强制终止；
- 完整 Windows 进程树清理；
- release automation 和 PyPI 发布；
- 真实 API E2E、浏览器验收和最终演示材料。

详见 [ROADMAP.md](ROADMAP.md)。

---

## 设计原则

1. **自己实现关键控制流**：模型协议、工具契约、Agent loop、错误反馈和 Session 不交给现成 Agent 框架；
2. **边界优先**：workspace、权限、超时和凭据保护优先于便利性；
3. **证据优先**：修改之后尽可能运行测试、构建或检查；
4. **错误可恢复**：工具错误进入模型上下文，推动下一轮修复；
5. **诚实交付**：已实现、已验证、待完成三类状态明确分开。

## 许可证

当前仓库尚未提供许可证文件。若将项目公开发布，请在确定授权条款后补充 `LICENSE`，并同步更新本节。
