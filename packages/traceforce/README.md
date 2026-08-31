# traceforce

`traceforce` 是 TraceForce 的产品层包：它把通用的 `traceforce-runtime` 和 `traceforce-llm` 装配为面向开发者的 Coding Agent。

## 提供什么

- `traceforce` console script；
- 一次性任务和交互式 REPL；
- Textual 全屏 TUI（`--tui`）；
- workspace 内的 `read`、`write`、`edit`、`bash`；
- 文件路径边界、写入队列、权限确认和危险命令过滤；
- 非交互 bash、超时和 Unix 进程组尽力清理；
- `AGENTS.md` / `CLAUDE.md` 项目说明加载；
- MCP stdio 客户端；
- Session 创建、列表、恢复和产品命令。

## 快速运行

```bash
cd packages/traceforce
uv sync

uv run traceforce \
  --workspace /path/to/project \
  "读取项目，运行相关测试，修复失败并汇报验证结果"
```

省略任务文本进入 REPL：

```bash
uv run traceforce --workspace /path/to/project
```

使用 Textual TUI：

```bash
uv run traceforce --workspace /path/to/project --tui
```

模型配置从 workspace 的 `.env` 或环境变量读取，例如：

```dotenv
TRACEFORCE_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=
```

不要把真实 API key 放在命令行、源码、Session、日志、截图、视频或仓库中。`packages/traceforce/.env.example` 是占位模板，复制到目标 workspace 后只在本地填写。

## 工具和权限

| 工具 | 默认行为 |
| --- | --- |
| `read` | 自动允许，只能读取 workspace 内文件 |
| `write` | 执行前确认，创建或覆盖文件 |
| `edit` | 执行前确认，只替换唯一匹配文本 |
| `bash` | 执行前确认，在 workspace 根目录运行非交互命令 |

`--yes` / `--no-confirm` 只跳过 bash、write、edit 的人工确认，不会关闭 workspace 边界、危险命令过滤和超时保护。

内置 bash 使用 EOF stdin、`CI=1`、`PIP_NO_INPUT=1`、`GIT_TERMINAL_PROMPT=0` 等非交互环境变量，并有 120 秒超时。它不是操作系统级沙箱；当前也不提供完整交互式 PTY。

## TUI 操作

TUI 显示 assistant streaming，并按可读节奏渐进呈现（仅调整 TUI 展示，不改变 runtime 或模型生成速度）；工具调用位于独立活动栏，宽屏并排显示在右侧，窄屏降级到主对话下方。对话和工具详情可选中复制。工具卡片支持展开、折叠、复制和关闭；关闭只影响可见 UI，不取消底层工具执行。任务输入支持终端多行粘贴：换行会合并为空格，粘贴后仍需按 Enter 发送。若终端没有发送 bracketed paste 事件，可直接在启动命令末尾传入带引号的任务文本。

输出区提供 `Copy output`、`Save output` 按钮，也可以输入 `/copy` 或 `/export`。复制和保存会先刷新尚未显示的流式文本。`/export` 会把当前可见对话保存到 workspace 内 `.traceforce/tui-transcript.txt`；这是剪贴板不可用时的可靠后备。模型错误的完整诊断保存到 `.traceforce/tui-error.txt`。这些文件被仓库忽略，但分享前仍应检查是否包含敏感信息。

```text
/help       显示帮助
/session    显示当前 workspace 和 Session ID
/sessions   列出会话
/clear      清除当前会话
/mcp        显示 MCP 状态
/exit       退出

Ctrl+C      无选区时取消当前任务
Ctrl+Shift+C 复制选区
Ctrl+L      清除可见日志
Ctrl+Q      退出 TUI
```

## MCP

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

产品层通过异步 stdio 连接 MCP server，并把远程工具转换成 runtime `Tool`。MCP server 可以执行本地高权限程序，只加载你信任的配置和 server。

## 开发与测试

```bash
cd packages/traceforce
uv sync
uv lock --check
uv run python -m pytest -q
uv build
```

测试使用 FakeLLM、Fake SDK、本地假 MCP server 和临时 workspace，不需要网络或真实 API key。当前离线测试数量为 55 项（以实际运行结果为准）。

产品层不复制 Agent loop：`CodingAgent` 负责工具装配，循环、Session、Context 和生命周期事件由 [`traceforce-runtime`](../traceforce-runtime/README.md) 提供；Provider 协议由 [`traceforce-llm`](../traceforce-llm/README.md) 提供。

## 关键模块

```text
src/traceforce/
├── cli.py             # argparse、REPL、模型和权限装配
├── tui.py             # Textual 全屏界面
├── agent.py           # CodingAgent 和四类工具装配
├── tools.py           # workspace 文件工具和非交互 bash
├── mcp.py             # MCP stdio 客户端
├── mutation_queue.py  # 文件变更队列
└── identity.py        # TraceForce 产品身份
```

更多架构、运行和演示说明见 [根 README](../../README.md) 与 [`docs/`](../../docs/README.md)。
