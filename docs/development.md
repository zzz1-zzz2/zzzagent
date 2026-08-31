# 开发指南

这份说明面向需要阅读源码、运行测试或扩展 TraceForce 的开发者。首次使用请先看根目录 [README.md](../README.md)。

## 开发环境

TraceForce 的三个包分别拥有自己的 `pyproject.toml` 和 `uv.lock`，当前按独立包同步依赖：

```bash
cd packages/traceforce-llm && uv sync
cd ../traceforce-runtime && uv sync
cd ../traceforce && uv sync
```

要求：Python 3.11+ 和 uv。真实模型运行还需要相应 Provider 的 API key 和模型名；离线测试不需要网络或真实凭据。

## 常用检查

在每个包目录执行：

```bash
uv lock --check
uv run python -m pytest -q
uv build
```

一次检查三个包：

```bash
for package in traceforce-llm traceforce-runtime traceforce; do
  (
    cd "packages/$package" || exit
    uv lock --check
    uv run python -m pytest -q
    uv build
  )
done
```

修改 Markdown、shell 或配置后，还应运行：

```bash
git diff --check
```

## 修改应该放在哪里？

| 需求 | 位置 |
| --- | --- |
| Provider API、统一消息或流式分片 | `packages/traceforce-llm/src/traceforce_llm/` |
| Agent loop、Tool、Session、Context、Hook | `packages/traceforce-runtime/src/traceforce_runtime/` |
| CLI、TUI、workspace 文件工具、权限或 MCP | `packages/traceforce/src/traceforce/` |
| 真实工程任务、准备脚本、独立裁判 | `evals/tasks/` |
| 架构、开发、评测和演示说明 | `docs/` |

不要为了让一个产品功能“看起来能用”而在 `evals/` 复制 Agent loop；也不要把 Textual UI 或 workspace 策略塞进通用 runtime。

## 本地运行

在目标 workspace 根目录放置未入库的 `.env`，然后从仓库运行：

```bash
uv run --project packages/traceforce traceforce \
  --workspace /path/to/project \
  "读取项目并完成一个小的、可验证的修改"
```

调试 TUI：

```bash
uv run --project packages/traceforce traceforce \
  --workspace /path/to/project --tui
```

为避免把密钥暴露给日志、Session 或 shell 历史，不要把 API key 放在命令行参数里。不要把包含真实 key 的 `.env`、`.mcp.json` 或 Session 加入版本控制。

## 测试约定

### 离线测试

测试应优先使用 FakeLLM、Fake SDK、临时目录和本地假 MCP server。这样可以稳定覆盖：

- provider 请求转换和响应归一化；
- streaming tool call 聚合；
- Agent loop 的工具调用、错误反馈和终止条件；
- Session 原子写盘、恢复、回退和分叉；
- workspace 路径检查、bash EOF、超时和权限；
- TUI 的事件映射、工具卡片、权限弹窗和取消。

### 真实 API

真实 API E2E 是单独的外部验收，不应冒充离线测试。运行前确认：

- 使用临时、可丢弃的 workspace；
- API key 来自环境变量或未入库 `.env`；
- 日志、Session、patch、截图和视频不包含凭据；
- 设置合理模型超时、迭代上限和费用边界。

### 文档同步

修改根 README 的能力、测试数字或命令时，同时检查 README.txt、包级 README 和 docs 中是否存在重复描述。状态词要区分：

- **已实现**：代码和测试已经存在；
- **已验证**：有明确的测试、独立 verifier 或人工记录；
- **待完成**：只列在 ROADMAP，不写成当前能力。

## 故障排查

### 找不到 `python`

项目命令使用 `uv run python`，不依赖系统是否存在裸 `python` 命令：

```bash
uv run python -m pytest -q
```

### 缺少 API key 或模型名

检查目标 workspace 的 `.env` 是否被加载，并确认变量名与 Provider 一致：`OPENAI_API_KEY`、`DEEPSEEK_API_KEY` 或 `ANTHROPIC_API_KEY`。TraceForce 不会在错误信息中打印 key。

### bash 命令等待输入

内置 bash 的 stdin 是 EOF，并设置 `CI=1`、`PIP_NO_INPUT=1`、`GIT_TERMINAL_PROMPT=0` 等变量。请使用工具支持的非交互参数，例如 `--yes`、`-y` 或 `--no-input`。需要完整交互式终端的命令目前不在支持范围内。

### TUI 似乎没有退出

全屏 TUI 在没有 `/exit` 或 Ctrl+Q 时会继续等待输入；这不代表 Agent loop 正在运行。Ctrl+C 在无选区时取消当前任务，Ctrl+Q 退出界面。

## 提交前清单

- [ ] 变更只落在正确的 Product / Runtime / LLM 边界；
- [ ] 新能力有离线测试或明确记录为何需要人工验收；
- [ ] 失败路径有可读错误反馈；
- [ ] workspace 越界和凭据保护没有被绕过；
- [ ] 文档没有把路线图、FakeLLM 测试或人工计划写成已完成；
- [ ] `git diff --check` 通过；
- [ ] 没有提交 `.env`、Session、workspace 生成物或真实证据中的秘密。
