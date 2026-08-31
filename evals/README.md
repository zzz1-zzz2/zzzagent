# TraceForce 评测任务

`evals/` 是 TraceForce 的证据层。`packages/` 保存产品和运行时的实现；这里的任务定义负责说明如何用真实软件工程任务检验这些实现，同时不在评测层复制 Agent loop。

## 评测约定

每个任务都遵循同一条边界：

```text
Prepare → Initial verification → Run TraceForce → Final verification → Collect Evidence → Reset
```

1. **Prepare（准备）** — 从仓库根目录运行任务的 `setup.sh`。脚本会在 `evals/workspaces/<task-name>` 下创建或恢复干净的 workspace。
2. **Initial verification（TraceForce 介入前的初始状态检查）** — 准备完成后立即运行 `verify.sh`，记录 TraceForce 开始工作前的状态。Bugfix 任务应证明问题仍存在并失败；Greenfield 任务应报告 workspace 为空或交付物尚不存在。
3. **Run TraceForce（运行 TraceForce）** — 只把生成的 workspace 交给 TraceForce。不要把任务目录或当前仓库根目录作为 TraceForce 的 workspace。
4. **Verify（验证）** — Agent 完成后再次运行任务的 `verify.sh`。该脚本是独立裁判，只有全部验收条件满足时才返回退出码 0。
5. **Collect Evidence（收集证据）** — 可以选择将脱敏后的 Session 总结、`git diff`/patch、测试输出、截图或短视频保存到 `evals/results/<task-name>/`。证据中绝不能保存 API key 或其他凭据。
6. **Reset（重置）** — 在开始下一次尝试前重新运行 `setup.sh`，恢复固定 revision 或空 workspace 的初始状态。

当前有意不实现 `evals/run.py`。setup 和 verify 脚本保持小而可审计，让 Agent 本身，而不是第二套 benchmark framework，继续作为被测系统。

## Before TraceForce / After TraceForce

这里的“初始状态检查”不是和其他 Agent 或模型比较的 benchmark baseline，而是确认同一个任务在 TraceForce 介入前后的状态变化：

| 任务 | Before TraceForce | After TraceForce |
| --- | --- | --- |
| 任务 01 tqdm | buggy revision；目标行为检查失败 | 目标行为恢复；独立 verifier 通过 |
| 任务 02 Sanic | middleware 顺序错误；独立检查失败 | middleware 顺序正确；独立 verifier 通过 |
| 任务 03 DevBoard | 空 workspace；静态页面不存在 | 原生 HTML/CSS/JS 页面生成；静态 verifier 通过，另做人工 UI 验收 |

因此评测要证明的是同一个任务的 `Initial state → TraceForce → Final state`，不包含第二个 Agent，也不要求排行榜式的竞品对照。
| 任务 | 覆盖内容 | Workspace | 独立验证 |
| --- | --- | --- | --- |
| [01 — tqdm bugfix](tasks/01-tqdm-bugfix/) | 现有 Python 仓库中的简单 API 回归修复 | `evals/workspaces/01-tqdm-bugfix/` | 定向 pytest 与独立行为断言 |
| [02 — Sanic bugfix](tasks/02-sanic-bugfix/) | 仓库代码阅读和 middleware 顺序语义修复 | `evals/workspaces/02-sanic-bugfix/` | 独立 blueprint middleware 注册顺序检查 |
| [03 — DevBoard greenfield](tasks/03-devboard-greenfield/) | 从空 workspace 创建原生静态前端 | `evals/workspaces/03-devboard-greenfield/` | 静态文件、响应式与交互检查和人工 UI 验收 |

前两个任务使用公开上游仓库的固定 buggy commit。它们的 setup 脚本只会在运行时 clone 对应仓库并 checkout 指定 revision，第三方完整源码不会提交到当前仓库。第三个任务从真正的空目录开始。

## 手动运行任务

在仓库根目录执行：

```bash
evals/tasks/01-tqdm-bugfix/setup.sh
evals/tasks/01-tqdm-bugfix/verify.sh  # 初始状态检查，预期失败

uv run --project packages/traceforce traceforce \
  --workspace "$PWD/evals/workspaces/01-tqdm-bugfix" \
  --tui \
  "Inspect the repository, fix the reported regression, and run the focused test."

evals/tasks/01-tqdm-bugfix/verify.sh  # 独立 PASS/FAIL
```

任务 02 和任务 03 使用相同流程，只需要替换任务目录和 workspace 路径。第一次 smoke run 可以只在你信任的 workspace 中使用 `--yes`；正常运行建议保留默认权限确认，以便同时检验权限交互。交给 Agent 的 user prompt 应只包含任务描述。不要把 `task.md`、setup 脚本、固定 revision 或 reference patch 放进生成的 workspace。

## 凭据与证据策略

模型凭据只能来自环境变量或本地未入库配置文件。不要将 API key 写入当前仓库、任务 workspace、Session、patch、截图、视频或结果压缩包。生成的 workspace 和结果目录已被 Git 忽略，但在分享证据前仍应人工检查内容。

`verify.sh` 不能相信 Agent 最后的文字总结。即使 Agent 声称任务完成，只要独立检查没有通过，就不能判定为 PASS；反过来，如果验证失败，也必须如实报告失败。
