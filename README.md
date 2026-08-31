# TraceForce Coding Agent

> 面向真实软件工程任务的可验证编程智能体
>
> **Developed by zzz** · GitHub: [zzz1-zzz2](https://github.com/zzz1-zzz2/zzzagent)

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-309%20passed-2ea44f)](#测试与验收)
[![Status](https://img.shields.io/badge/status-development-orange)](#当前范围)

TraceForce 是由 **zzz** 开发的、面向真实软件工程任务的 Coding Agent。它不只是对话窗口，也不依赖现成的 Agent 框架或 Agent SDK，而是自己实现了模型适配、工具调用循环、文件操作、命令执行、权限确认、上下文管理、会话持久化和验证反馈。

它的目标是让模型真正参与软件工程工作：

```text
读取项目 → 分析问题 → 修改文件 → 运行验证 → 根据结果修复 → 汇报证据
```

---

## 项目亮点

### 1. 真正可执行的编程智能体

TraceForce 内置四类 Coding 工具：

| 工具 | 用途 | 默认权限 |
| --- | --- | --- |
| `read` | 分页读取工作区文件 | 自动允许 |
| `write` | 创建或覆盖文件 | 执行前确认 |
| `edit` | 基于唯一文本匹配修改文件 | 执行前确认 |
| `bash` | 在工作区中运行测试、构建和检查命令 | 执行前确认 |

模型不直接访问文件系统。每次工具调用都经过参数校验、workspace 边界检查和运行时错误处理。

### 2. Evidence-first loop

TraceForce 不把模型的第一段回答当作任务完成，而是要求任务经过可观察的交付闭环：

1. **Inspect**：读取相关文件、项目说明和现有实现；
2. **Plan**：选择最小、可解释的修改路径；
3. **Change**：通过受保护的文件工具实施变更；
4. **Verify**：运行测试、构建或静态检查；
5. **Explain**：汇报实际修改、验证结果和剩余风险。

工具错误会作为结构化观察反馈给模型。模型可以根据错误修正路径、参数或实现，而不是因为一次工具异常直接退出。

### 3. Workspace contract

每次运行都绑定一个明确的 workspace：

- 相对路径从 workspace 根目录解析；
- `resolve()` 后检查路径是否仍在 workspace 内；
- `../`、越界绝对路径和符号链接越界访问会被拒绝；
- `bash` 在 workspace 中执行，使用 EOF stdin 和非交互环境变量，设置超时并在 Unix 上按进程组清理；
- 写操作使用按文件锁，避免同一文件并发覆盖；
- 非交互环境默认拒绝高风险工具调用；
- `--yes` 只跳过确认，不会关闭路径检查、危险命令过滤和超时保护。

### 4. 可恢复的会话

Session 以 JSONL 文件保存到目标项目的 `.traceforce/sessions/`：

- 每条消息带 `id` 和 `parent_id`；
- 支持恢复、回退和分叉；
- 大型工具输出可以独立落盘；
- 上下文压缩只改变发送给模型的视图，不破坏真实历史；
- Ctrl+C 在安全点停止运行，不把不完整的 assistant 输出写入会话。

---

## 架构

TraceForce 由三个独立 Python 包组成：

```text
┌────────────────────────────────────────────────────────────┐
│ traceforce                                                  │
│ CodingAgent · CLI · REPL · TUI · 文件工具 · 权限确认 · MCP  │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│ traceforce-runtime                                          │
│ Agent Loop · Tool Registry · Hooks · Session · Context     │
│ Skills · Subagents · Tasks · Extensions · Plugins · Memory │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│ traceforce-llm                                              │
│ Message · Response · StreamChunk · Provider Adapters        │
│ OpenAI · DeepSeek · Anthropic · Tool-call Aggregation       │
└────────────────────────────────────────────────────────────┘
```

`evals/` 是独立的验收层，不参与产品运行时：它只保存任务定义、workspace 准备脚本、独立验证脚本和可选结果证据。评测按 `Prepare → Baseline → Run Agent → Verify → Collect Evidence → Reset` 执行，运行时 workspace 和结果默认被 Git 忽略。详见 [evals/README.md](evals/README.md)。

### `traceforce-llm`

模型边界层，负责：

- 统一同步、异步和流式调用接口；
- OpenAI、DeepSeek、Anthropic Provider 适配；
- 统一 `Message`、`Response`、`StreamChunk`；
- 聚合流式 tool call 分片；
- 归一化 usage 和 finish reason。

### `traceforce-runtime`

通用 Agent 运行时，负责：

- 原生 `asyncio` ReAct 循环；
- Pydantic 参数 Schema 和 `ToolResult` 错误反馈；
- 只读工具并发、写工具串行和保序回填；
- Agent、Turn、Message、Tool、Context 生命周期事件；
- JSONL 树状 Session 和上下文压缩；
- Skills、Subagents、Tasks、Extensions、Plugins、Memory；
- steering / follow-up 动态消息队列。

### `traceforce`

面向开发者的产品层，负责：

- `traceforce` console script；
- 当前目录 workspace 启动；
- `read`、`write`、`edit`、`bash`；
- 终端流式输出和工具调用展示；
- 权限确认；
- 项目说明加载（`AGENTS.md`、`CLAUDE.md`）；
- MCP stdio 客户端；
- Session 列表和恢复；
- Textual 全屏 TUI（`--tui`）：对话流、工具卡片、异步权限确认、取消和 Session 命令。

---

## 快速开始

### 环境要求

运行 TraceForce 本身需要：

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- 一个兼容的模型 API

运行 `evals/` 中的完整评测还需要：

- Git，以及能够访问 GitHub 的网络环境（任务 01/02 会动态准备上游仓库）；
- Node.js 和 npm（任务 03 的 React + Vite greenfield 项目）；
- 能够访问 npm registry 的网络环境（安装前端依赖）；
- Chrome、Firefox 或其他浏览器（任务 03 的人工 UI 验收，机器 verifier 不依赖浏览器）。

评测 setup 脚本会把任务专用 Python 依赖安装到生成 workspace 内的 `.eval-venv`，不会修改宿主机的全局 Python 环境。TraceForce 可以创建和配置项目级环境，但不会替宿主机安装 Python、Node.js、npm 或系统包。

### 安装

仓库当前采用三个独立 uv 包。首次使用时分别同步依赖：

```bash
cd packages/traceforce-llm
uv sync

cd ../traceforce-runtime
uv sync

cd ../traceforce
uv sync
```

开发时可以直接在产品包目录使用 `uv run`。

### 配置模型

TraceForce 不接受命令行 API key，也不会把 key 打印到终端。复制模板到目标 workspace 的 `.env`，并只在本地填写配置：

```bash
cp packages/traceforce/.env.example /path/to/your-project/.env
```

示例变量：

```dotenv
TRACEFORCE_PROVIDER=openai
TRACEFORCE_MODEL=your-model-name
TRACEFORCE_BASE_URL=
OPENAI_API_KEY=
```

也支持 Provider 专用变量：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=your-model-name
```

`.env` 已被 Git 忽略。请不要把真实凭据写入源码、README、Session、截图或演示视频。

### 在当前项目目录启动

如果当前 shell 位于目标项目目录，可以直接启动：

```bash
cd /path/to/your-project
/path/to/traceforce/checkout/packages/traceforce/.venv/bin/traceforce
```

从仓库目录开发运行：

```bash
cd packages/traceforce
uv run traceforce --workspace /path/to/your-project
```

### 执行一次性任务

```bash
uv run traceforce \
  --workspace /path/to/your-project \
  --yes \
  "运行测试，定位失败原因并修复最小必要代码"
```

`--yes` 仅适用于你信任的 workspace。演示和日常开发建议保留默认确认行为。

### 交互式 REPL

不提供 prompt 时进入 REPL：

```bash
uv run traceforce --workspace /path/to/your-project
```

内置命令：

```text
/help       显示帮助
/session    显示当前 workspace 和会话 ID
/sessions   列出已保存会话
/clear      清空当前会话并保留配置
/exit       退出
```

支持通过 `--session ID_OR_PREFIX` 恢复会话：

```bash
uv run traceforce --workspace /path/to/your-project \
  --session 20260830-123456-ab12cd34
```

运行期间按 Ctrl+C 会请求 Agent 在安全点停止当前任务，并返回 REPL。当前版本是合作式取消；正在运行的外部子进程不会保证立即被进程组级终止。

### Textual 全屏界面

保留纯终端模式作为默认入口；使用 `--tui` 启动全屏 Textual 界面：

```bash
uv run traceforce --workspace /path/to/your-project --tui
uv run traceforce --workspace /path/to/your-project --tui "运行测试并修复失败"
```

TUI 展示 workspace/session 侧栏、assistant 流式输出、可选中复制的对话与工具详情、可折叠的
工具状态卡片，并在界面内提供 Allow/Deny 权限弹窗。已完成的卡片默认折叠，可使用 `Copy details`
复制详情或 `Close` 隐藏卡片；关闭只影响可见 UI，不取消底层工具调用。可使用 `/help`、`/session new`、
`/session ID`、`/sessions`、`/clear`、`/mcp` 和 `/exit`；Ctrl+C 在无选区时取消当前任务，有选区时复制，
Ctrl+Shift+C 明确复制选区，Ctrl+L 清除可见日志，Ctrl+Q 退出。终端剪贴板支持取决于终端的 OSC52
能力。内置 bash 使用 EOF stdin、非交互环境变量、超时和 Unix 进程组清理；需要交互式输入的命令
不会获得 TUI stdin，应改用 `--yes`、`-y` 或 `--no-input` 等非交互参数。`--tui` 不改变 runtime 的
Agent loop、workspace 边界或工具权限策略。

---

## CLI 参数

```text
--workspace PATH          工作区目录，默认当前目录
--session ID              恢复指定会话或唯一前缀
--provider NAME           openai / deepseek / anthropic
--model NAME              模型名称
--base-url URL            OpenAI 兼容网关地址
--timeout SECONDS         单次模型请求超时
--max-retries N           模型请求最大重试次数
--max-tokens N            模型输出 token 上限
--yes                     跳过 bash/write/edit 确认
--max-iterations N        限制一次任务的 Agent 迭代次数
--tui                     使用 Textual 全屏界面
--version                 打印版本
```

查看完整帮助：

```bash
uv run traceforce --help
uv run python -m traceforce --help
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

TraceForce 会通过异步 stdio 连接 MCP server，并将远程工具转换为本地 runtime `Tool`。在 REPL 中使用：

```text
/mcp
```

查看已连接服务和工具状态。

MCP server 可以执行任意本地程序，属于独立的高权限信任边界。只加载你信任的配置和 server，不要把不受信任的 MCP server 放进演示 workspace。

---

## 测试与验收

三个包分别执行锁文件检查、离线测试和 wheel 构建：

```bash
cd packages/traceforce-llm
uv lock --check
uv run python -m pytest -q
uv build

cd ../traceforce-runtime
uv lock --check
uv run python -m pytest -q
uv build

cd ../traceforce
uv lock --check
uv run python -m pytest -q
uv build
```

当前测试套件覆盖：

- Provider 请求和响应转换；
- 流式文本与 tool call 聚合；
- ReAct 循环和终止条件；
- 工具 Schema、批量执行和错误反馈；
- Hook 拦截与事件生命周期；
- Session 恢复、回退、分叉和原子写盘；
- Context 压缩和工具结果落盘；
- Skills、Subagents、Tasks、Extensions、Plugins、Memory；
- workspace 路径安全和文件修改；
- CLI presenter、权限确认和 MCP 集成；
- Textual TUI mount、streaming、tool cards、异步权限弹窗、复制/关闭交互和取消控制。

当前验收基线为：`traceforce-llm` 36 项、`traceforce-runtime` 228 项、`traceforce` 45 项，共 309 项测试。测试使用 FakeLLM、Fake SDK、本地假 MCP server 和临时 workspace，不需要网络或真实 API key。

---

## 当前范围

当前版本已经提供可运行的终端 Coding Agent、Textual 全屏 TUI，以及可复用的异步 Agent runtime。以下能力仍在路线图中，不能视为当前版本已实现：

- typed trajectory；
- 独立的 workspace 变更追踪与 evidence 数据模型；
- `WorkspaceChangeTracker` 和 `traceforce check`；
- 完整交互式 PTY 终端转发；
- 任意第三方同步工具的强制终止；
- 完整 release automation 和 PyPI 发布流程。

详见 [ROADMAP.md](ROADMAP.md)。

---

## 文档与代码结构

根目录 README 是项目使用说明，未来计划见 [ROADMAP.md](ROADMAP.md)。源码按能力拆分为三个独立包：

```text
packages/
├── traceforce-llm/       # Provider 适配和统一模型协议
├── traceforce-runtime/   # Agent 循环、工具、Session 和扩展运行时
└── traceforce/           # Coding Agent、CLI、文件工具和 MCP
```

每个包拥有自己的 `pyproject.toml`、`uv.lock`、源码和离线测试。实现细节以源码和测试为准。

---

## 设计原则

TraceForce 坚持以下原则：

1. **自己实现关键控制流**：模型调用、工具协议、Agent 循环、错误反馈和 Session 不交给现成 Agent 框架；
2. **边界优先**：workspace、权限、超时和凭据保护先于便利性；
3. **证据优先**：修改之后必须尽可能运行测试、构建或检查；
4. **错误可恢复**：错误进入模型上下文，推动下一轮修复；
5. **诚实交付**：未实现的能力明确列出，不把路线图写成现成功能。

---

## 许可证

当前仓库尚未提供许可证文件。若将项目公开发布，请在确定授权条款后补充 `LICENSE`，并同步更新本节。

## 致谢

TraceForce 的实现坚持独立的模块边界和可测试性。Provider SDK 仅用于连接模型服务，不承担 Agent 控制流；MCP SDK 仅用于协议连接，不承担 workspace 权限策略。
