# TraceForce 演示脚本

这是一份适合推免答辩、项目汇报或本地录屏的诚实演示流程。它把“产品能做什么”“如何证明”和“当前还缺什么”分开，避免把一次成功对话误说成完整能力证明。

## 演示前准备

1. 准备一个可丢弃的 demo workspace，不要使用包含隐私或生产凭据的项目；
2. 确认 Python 3.11+、uv、Git 和目标模型 API 可用；
3. 将 API key 放在未入库 `.env` 或环境变量中；
4. 检查终端支持 OSC52（如需演示复制）；
5. 预先运行三包离线测试，保存真实输出；
6. 如果演示评测任务，先运行 setup 和 TraceForce 介入前的初始状态检查。

示例配置：

```bash
export TRACEFORCE_PROVIDER=deepseek
export DEEPSEEK_MODEL=deepseek-chat
export DEEPSEEK_API_KEY='只在本地 shell 中设置，不要写入脚本'
```

不要在录屏、截图、终端回放或 Session 中展示上述变量的真实值。

## 建议演示顺序

### 1. 先讲边界

用一句话介绍：

> TraceForce 是由 zzz 开发的 Coding Agent，目标是让模型在受保护的 workspace 中完成“读取、修改、验证、修复和汇报证据”的工程闭环。

然后展示仓库结构：

```text
packages/traceforce-llm       模型协议和 Provider 适配
packages/traceforce-runtime   Agent loop、工具、Context、Session
packages/traceforce            CLI、TUI、workspace 工具、权限、MCP
evals/                         独立任务和 verifier
docs/                          架构、开发、评测和演示说明
```

强调：这里没有使用现成 Agent 编排框架或 Agent SDK；模型厂商 SDK 只负责连接模型服务。

### 2. 展示产品入口

先查看帮助：

```bash
uv run --project packages/traceforce traceforce --help
```

再启动一个一次性任务或 REPL：

```bash
uv run --project packages/traceforce traceforce \
  --workspace "$PWD/demo-workspace" \
  "先读取项目文件，再说明你准备如何验证一个小修改"
```

现场可以展示：workspace、Session ID、模型流式输出，以及 Agent 如何先使用 `read` 再决定下一步。

### 3. 展示权限和工具循环

使用默认确认模式，让 Agent 做一个小而可逆的修改。展示：

- `read` 自动执行；
- `write` / `edit` / `bash` 执行前出现确认；
- 工具参数和结果在终端或 TUI 中可见；
- bash 运行测试或检查，而不是只凭模型口头判断；
- 错误结果回到模型后，模型继续修复。

不要为了追求流畅而默认使用 `--yes`；如果使用，明确说明它只跳过确认，不会关闭 workspace 边界、危险命令过滤和超时保护。

### 4. 展示 TUI

```bash
uv run --project packages/traceforce traceforce \
  --workspace "$PWD/demo-workspace" --tui
```

建议演示：

1. 输入一个需要读取和检查的小任务；
2. 展示 assistant streaming；
3. 在权限弹窗中选择 Allow 或 Deny；
4. 展开、折叠和复制工具详情；
5. 关闭已完成的 ToolCard，说明关闭只影响可见 UI；
6. 按 Ctrl+C 取消正在运行的任务；
7. 用 `/session`、`/sessions` 和 `/clear` 展示 Session 交互。

说明 TUI 不是另一套 Agent：它只是 runtime 事件的产品层消费者，Agent loop、workspace 边界和权限策略不因 `--tui` 改变。

### 5. 展示可复现评测

选择一个任务，按协议演示：

```bash
evals/tasks/01-tqdm-bugfix/setup.sh
evals/tasks/01-tqdm-bugfix/verify.sh  # 初始状态应失败
```

把 workspace 交给 TraceForce，完成后再次执行：

```bash
evals/tasks/01-tqdm-bugfix/verify.sh
```

最后展示 verifier 的 PASS/FAIL，而不是只展示 Agent 的最终总结。任务 03 还需要浏览器人工检查桌面和窄屏布局；shell verifier 只判断 package manifest 和 production build。

## 答辩时的诚实表述

### 可以明确说已实现

- 三包职责分层；
- 原生异步 Agent loop；
- Provider 适配和流式 tool-call 聚合；
- read/write/edit/bash 工具；
- workspace 路径边界和权限确认；
- 错误反馈、Session、Context、MCP 和 Textual TUI；
- 三个任务定义、setup 和独立 verifier；
- 313 项离线测试记录（以当前仓库实际运行结果为准）。

### 必须说明仍有限制

- bash 不是操作系统级沙箱；
- 当前没有完整交互式 PTY；
- 第三方同步工具和 Windows 进程树不保证立即强制终止；
- typed trajectory、WorkspaceChangeTracker 和 `traceforce check` 尚未完成；
- 真实 API E2E、浏览器验收和最终演示材料需要单独产生证据；
- 当前没有 PyPI 发布和完整 release automation。

## 演示结束检查

结束录屏或打包前：

- [ ] 删除或隔离 `.env`、Session 和临时 workspace；
- [ ] 搜索输出、截图和视频中是否出现 API key 或 token；
- [ ] 确认只展示真实运行过的测试和 verifier 结果；
- [ ] 将人工 UI 验收和机器 verifier 分开记录；
- [ ] 不把 demo workspace 或 evals/results 中的真实内容提交到仓库。
