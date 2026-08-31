# 评测指南

`evals/` 是 TraceForce 的独立证据层：它回答“Agent 是否能在真实软件工程任务中留下正确结果”，而不是重新实现一套 Agent。任务定义位于 [`evals/tasks/`](../evals/tasks/)，产品和运行时实现位于 [`packages/`](../packages/)。

## 统一协议

每个任务都按以下顺序运行：

```text
Prepare → Initial verification → Run TraceForce → Final verification → Collect Evidence → Reset
```

### Prepare

运行任务目录的 `setup.sh`。它负责删除旧 workspace、准备固定 buggy revision 或创建空目录，并安装任务需要的项目级依赖。第三方源码不提交到当前仓库。

### Initial verification：TraceForce 介入前

在运行 TraceForce 前立即执行 `verify.sh`，记录任务的初始状态：

- bugfix 任务应证明问题仍存在并失败；
- greenfield 任务应报告 workspace 为空或交付物尚不存在；
- 如果初始状态检查意外通过，应先检查 verifier 和 setup，而不是继续运行 TraceForce。

### Run TraceForce

只将生成的 workspace 交给 TraceForce。任务目录、固定 revision、reference patch 和当前仓库根目录不应放进被测 workspace；否则任务会泄露答案或扩大 TraceForce 可见范围。

### Verify

Agent 完成后再次执行 `verify.sh`。verifier 必须独立读取 workspace 并返回 PASS/FAIL；不能相信 Agent 最后的文字总结，也不能只检查是否存在某个文件。

### Collect Evidence

可以在 `evals/results/<task-name>/` 保存脱敏后的：

- Agent summary；
- `git diff` 或 patch；
- 测试/构建输出；
- 截图或短视频；
- 人工 UI 验收记录。

证据不是默认提交物。分享前必须人工检查 API key、token、`.env` 内容、Session 和用户隐私。

### Reset

下一次尝试前重新运行 `setup.sh`，恢复固定 revision 或空 workspace 的初始状态。不要在同一 workspace 上叠加多次实验并把结果当作独立证据。

## Before TraceForce / After TraceForce

这里的初始状态检查不是比较其他 Agent 的 benchmark baseline，而是记录同一个任务在 TraceForce 介入前后的变化：

| 任务 | Before TraceForce | After TraceForce |
| --- | --- | --- |
| 任务 01 tqdm | buggy revision；目标行为检查失败 | 目标行为恢复；独立 verifier 通过 |
| 任务 02 Sanic | middleware 顺序错误；独立检查失败 | middleware 顺序正确；独立 verifier 通过 |
| 任务 03 DevBoard | 空 workspace；静态页面不存在 | 原生 HTML/CSS/JS 页面生成；静态 verifier 通过，并完成人工 UI 验收 |

本项目只有一个被测 Agent：TraceForce。这里不引入第二个 Agent，也不做竞品排行榜；证据链是 `Initial state → TraceForce → Final state`。


| 任务 | 目标 | 机器验证 | 人工补充 |
| --- | --- | --- | --- |
| [01 — tqdm bugfix](../evals/tasks/01-tqdm-bugfix/) | 修复 `tenumerate` 非零起始值语义 | 定向 pytest + 独立行为断言 | 修改范围和测试证据 |
| [02 — Sanic bugfix](../evals/tasks/02-sanic-bugfix/) | 恢复 Blueprint response middleware 顺序 | 独立 registry 顺序检查 | 仓库推理过程和 patch |
| [03 — DevBoard greenfield](../evals/tasks/03-devboard-greenfield/) | 从空目录创建原生静态 DevBoard | 静态文件、本地资源、响应式样式与交互脚本 | 浏览器中的桌面/窄屏 UI 验收 |

任务 01/02 在运行时 clone 公开上游仓库并 checkout 固定 buggy commit；任务 03 从真正空目录开始。机器 verifier 和人工验收分别记录，不把视觉质量伪装成 shell 能完整判断的契约。

## 手动运行示例

以任务 01 为例，从仓库根目录执行：

```bash
evals/tasks/01-tqdm-bugfix/setup.sh
evals/tasks/01-tqdm-bugfix/verify.sh  # 预期失败

uv run --project packages/traceforce traceforce \
  --workspace "$PWD/evals/workspaces/01-tqdm-bugfix" \
  --tui \
  "Inspect the repository, fix the reported regression, and run the focused test."

evals/tasks/01-tqdm-bugfix/verify.sh  # 独立 PASS/FAIL
```

任务 02 和任务 03 采用相同流程。正常运行建议保留默认权限确认；只在信任 workspace 且明确接受风险时使用 `--yes`。交给 Agent 的 prompt 应只包含 task.md 的任务内容，不应包含 verifier、reference patch 或答案提示。

## 环境前置条件

运行 TraceForce 本身：

- Python 3.11+；
- uv；
- 兼容的模型 API。

运行完整评测：

- Git 和 GitHub 网络访问；
- Node.js、npm 和 npm registry 网络访问；
- 任务 03 人工验收所需的浏览器。

setup 脚本使用 workspace 内的 `.eval-venv` 安装 Python 依赖，不修改宿主机全局 Python 环境。Agent 可以创建项目级 `package.json`、虚拟环境和依赖配置，但不会替宿主机安装系统工具。

## 结果判定原则

一次评测至少应保留以下信息：

```text
任务名称
setup revision / 空 workspace 说明
初始状态检查结果
Agent 使用的 workspace
verify 结果和退出码
测试或构建输出位置
人工验收（如适用）
是否包含脱敏 patch/summary
```

不要用以下内容代替独立证据：

- Agent 说“已完成”；
- 只展示最终文件截图；
- 只展示离线单元测试；
- 只展示 `git diff` 没有运行 verifier；
- 把真实 API 请求是否成功写成离线测试记录。

## 安全检查

评测前后都要确认：

- API key 只来自环境变量或未入库配置文件；
- key 没有进入 workspace、Session、日志、patch、截图、视频或压缩包；
- workspace 和 results 的实际内容未被 Git 跟踪；
- `verify.sh` 没有执行危险命令或修改被测结果；
- 任务目录没有泄露 reference patch。

当前不实现统一 `evals/run.py`。保持脚本短小、透明、可审计，正是为了让评委能看懂每项验收究竟检查了什么。
