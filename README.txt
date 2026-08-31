TraceForce Coding Agent
=======================

面向真实软件工程任务的可验证编程智能体
由 zzz 开发 · GitHub: https://github.com/zzz1-zzz2/zzzagent

TraceForce 是一个可以实际读取项目、修改文件、执行检查并根据结果继续修复的 Coding Agent。它不是只返回建议的聊天窗口，也不依赖现成 Agent 编排框架或 Agent SDK；模型适配、工具调用循环、上下文视图、Session、权限和产品交互都在本仓库中实现。

核心闭环：

  读取项目 -> 分析问题 -> 修改文件 -> 运行测试/构建
  -> 根据错误继续修复 -> 汇报证据

项目结构
--------

TraceForce 由三个产品包和一个独立验收层组成：

  traceforce-llm
    模型边界。负责 OpenAI、DeepSeek、Anthropic 和 OpenAI 兼容网关，
    统一 Message、Response、StreamChunk，并聚合流式 tool call。
    不负责 workspace、工具执行或 Agent loop。

  traceforce-runtime
    通用异步运行时。负责原生 asyncio ReAct 循环、Tool、Pydantic
    参数 Schema、ToolResult、生命周期事件、Context、JSONL Session，
    以及 Skills、Subagents、Tasks、Extensions、Plugins、Memory 等扩展。
    不负责 CLI、TUI 或具体 workspace 权限策略。

  traceforce
    面向开发者的产品层。负责 CodingAgent、console script、REPL、
    Textual TUI、read/write/edit/bash、workspace 边界、权限确认、
    项目说明加载和 MCP stdio 客户端。

  evals/
    独立证据层，只定义如何验证实现有效，不复制 Agent loop。
    任务流程为 Prepare -> Initial verification -> Run TraceForce ->
    Final verification -> Collect Evidence -> Reset。

能力概览
--------

内置四类 Coding 工具：

  read   分页读取 workspace 内文件，默认自动允许
  write  创建或覆盖文件，执行前确认
  edit   对唯一匹配文本做精确替换，执行前确认
  bash   在 workspace 根目录运行测试、构建和检查命令，执行前确认

工具调用会经过参数校验、workspace 边界检查和运行时错误处理。工具失败会以结构化 ToolResult 写回模型上下文，模型可以据此修正下一轮操作。

Agent loop 自己实现：

  UserInput -> AgentStart -> ContextManager.prepare()
  -> LLM streaming -> MessageUpdate -> 解析 tool_calls
  -> 权限 Hook -> ToolRegistry.execute_batch()
  -> ToolResult 写回消息 -> 下一轮模型调用
  -> 没有 tool call 时结束 -> AgentEnd

模型没有 tool call 时自然结束；产品 CLI 默认最多 30 次迭代，防止异常循环。用户可以使用 Ctrl+C 请求合作式取消。

安全边界
--------

所有文件路径解析后都必须位于 workspace 根目录；../、越界绝对路径和符号链接越界访问会被拒绝。bash 在 workspace 中运行，stdin 使用 EOF，设置常见非交互环境变量，并有 120 秒超时；Unix 上按进程组尽力清理超时或取消的子进程。

bash 不是操作系统级沙箱。当前版本不提供完整 PTY，也不能保证所有第三方同步工具、通过 /dev/tty 绕过 stdin 的程序或 Windows 进程树都能立即终止。MCP server 可以执行本地高权限程序，只应加载信任的 .mcp.json。

安装与运行
----------

运行 TraceForce 本身需要 Python 3.11+、uv 和兼容的模型 API。完整运行 evals 还需要 Git/GitHub 网络、Node.js、npm、npm registry 网络和浏览器。

分别安装三个包：

  cd packages/traceforce-llm && uv sync
  cd ../traceforce-runtime && uv sync
  cd ../traceforce && uv sync

复制配置模板到目标 workspace：

  cp packages/traceforce/.env.example /path/to/your-project/.env

本地填写模型配置，例如：

  TRACEFORCE_PROVIDER=openai
  TRACEFORCE_MODEL=your-model-name
  OPENAI_API_KEY=

也可以使用 DEEPSEEK_API_KEY、DEEPSEEK_MODEL、ANTHROPIC_API_KEY 等变量。API key 只能通过环境变量或未入库配置文件提供；不得写入仓库、README、Session、patch、截图、视频或最终压缩包。TraceForce 不接受命令行明文 key，也不会打印 key。

执行一次性任务：

  uv run --project packages/traceforce traceforce \
    --workspace /path/to/your-project \
    "读取项目，定位失败测试的原因，修改最小必要代码并运行测试验证"

省略任务文本进入 REPL：

  uv run --project packages/traceforce traceforce \
    --workspace /path/to/your-project

信任 workspace 且需要跳过写操作确认时使用 --yes：

  uv run --project packages/traceforce traceforce \
    --workspace /path/to/your-project --yes "运行测试并修复失败"

--yes 只跳过 bash、write、edit 的人工确认，不会关闭路径检查、危险命令过滤或超时保护。

Textual TUI
-----------

使用 --tui 启动全屏界面：

  uv run --project packages/traceforce traceforce \
    --workspace /path/to/your-project --tui

TUI 提供 workspace、Session 和 Agent 状态，assistant 流式输出按可读节奏渐进显示（仅调整 TUI 展示，不改变 runtime 或模型生成速度），并将工具调用放在独立活动栏：宽屏显示在右侧，窄屏降级到下方活动区。对话和工具详情可选中复制；工具卡片支持展开、折叠、复制和关闭，关闭只影响可见 UI，不取消底层工具执行。任务输入支持终端多行粘贴：换行会合并为空格，粘贴后仍需按 Enter 发送；若终端不支持 bracketed paste，可在启动命令末尾直接传入带引号的任务文本。

输出区提供 Copy output、Save output 按钮，也可以使用 /copy 和 /export。/export 将当前可见对话保存到 workspace/.traceforce/tui-transcript.txt；模型错误的完整诊断保存到 workspace/.traceforce/tui-error.txt。复制会先刷新尚未显示的流式文本；剪贴板依赖终端 OSC52，/export 和 tui-transcript.txt 是可靠后备。错误诊断和导出文件分享前必须检查是否包含敏感信息。

常用命令和快捷键：

  /help       显示帮助
  /session    显示当前 workspace 和 Session ID
  /sessions   列出已保存 Session
  /clear      清空当前会话
  /copy       复制完整可见对话
  /export     保存完整可见对话
  /mcp        显示 MCP 服务状态
  /exit       退出
  Ctrl+C      无选区时取消任务
  Ctrl+Shift+C 复制选区
  Ctrl+L      清除可见日志
  Ctrl+Q      退出 TUI

工具卡片完成后默认折叠；关闭只影响可见 UI，不取消底层工具调用。剪贴板复制能力取决于终端 OSC52 支持；任务粘贴能力取决于终端是否发送 bracketed paste 事件。需要交互输入的命令不会获得 TUI stdin，应使用 --yes、-y 或 --no-input 等非交互参数。

Session
-------

Session 默认保存在目标 workspace 的 .traceforce/sessions/，使用 JSONL 保存消息和父子关系，支持恢复、回退和分叉。上下文压缩只改变发送给模型的视图，不删除真实历史；取消时不会把不完整的 assistant 流写入会话。

MCP
---

在目标 workspace 根目录创建未入库的 .mcp.json，配置 mcpServers 的 command、args 和 env。TraceForce 通过异步 stdio 连接 MCP server，将远程工具转换为 runtime Tool，并在 /mcp 中显示状态。MCP 属于独立的高权限信任边界，只加载信任的 server。

可复现评测
----------

evals/ 只负责定义如何证明实现有效。任务目录只提交 task.md、setup.sh 和 verify.sh；第三方源码在运行时 clone，Greenfield 任务在运行时创建空 workspace；evals/workspaces/ 和 evals/results/ 不提交实际内容。

  任务 01  tqdm bugfix
    阅读现有 Python 仓库并修复简单 API 回归；定向测试和独立行为断言。
  任务 02  Sanic bugfix
    推理 Blueprint middleware 注册顺序；独立 registry 顺序检查。
  任务 03  DevBoard greenfield
    从空目录配置 React + Vite 并完成生产构建；检查 package.json、
    build script 和 npm run build，视觉质量由人工浏览器验收。

Before TraceForce / After TraceForce
-----------------------------------

这里的初始状态检查不是和其他 Agent 或模型比较的 benchmark baseline，而是确认同一个任务在 TraceForce 介入前后的状态变化：

  任务 01 tqdm
    Before: buggy revision，目标行为检查失败
    After: 目标行为恢复，独立 verifier 通过
  任务 02 Sanic
    Before: middleware 顺序错误，独立检查失败
    After: middleware 顺序正确，独立 verifier 通过
  任务 03 DevBoard
    Before: 空 workspace，package.json 不存在
    After: React + Vite 项目生成，production build 通过，另做人工 UI 验收

这里只有一个被测 Agent：TraceForce。证据链是 Initial state -> TraceForce -> Final state，不包含第二个 Agent 或竞品排行榜。

开始评测前必须先做 TraceForce 介入前的初始状态检查。TraceForce 的最终总结不能替代独立 verifier。详见 evals/README.md 和 docs/evaluation.md。

测试与构建
----------

  for package in traceforce-llm traceforce-runtime traceforce; do
    (cd "packages/$package" && uv lock --check && uv run python -m pytest -q && uv build)
  done

记录的离线测试数量：traceforce-llm 36 项，traceforce-runtime 228 项，traceforce 55 项，共 319 项。测试使用 FakeLLM、Fake SDK、本地假 MCP server 和临时 workspace，不需要网络或真实 API key。

测试统计不等于真实 API E2E、浏览器人工验收或发布证据；这些内容必须单独记录，不能虚构。

文档地图
--------

  README.md       产品定位、快速开始、架构和能力边界
  README.txt      纯文本同步入口
  docs/README.md  文档导航和推荐阅读顺序
  docs/architecture.md  模块职责、Agent loop、事件和数据边界
  docs/development.md   本地开发、测试、构建和故障排查
  docs/evaluation.md    评测协议、任务证据和复现要求
  docs/demo.md          推免答辩和现场演示的诚实操作脚本
  ROADMAP.md      尚未交付的后续能力

当前范围
--------

已经提供：可运行的终端 Coding Agent、REPL、Textual TUI、原生异步 Agent loop、模型 Provider 适配、工具和错误反馈、workspace 边界、权限、非交互 bash、超时、Session、Context、扩展机制、MCP，以及三个可复现评测任务。

仍未完成：typed trajectory、WorkspaceChangeTracker、独立 evidence 数据模型、traceforce check、完整交互式 PTY、任意第三方同步工具强制终止、完整 Windows 进程树清理、release automation、PyPI 发布、真实 API E2E、浏览器验收和最终演示材料。详见 ROADMAP.md。

设计原则
--------

1. 自己实现关键控制流，不使用现成 Agent 编排框架或 Agent SDK。
2. workspace、权限、超时和凭据保护优先于便利性。
3. 修改后尽可能运行测试、构建或检查。
4. 工具错误进入模型上下文，推动下一轮修复。
5. 已实现、已验证、待完成三类状态明确分开。

许可证
------

当前仓库尚未提供许可证文件。若将项目公开发布，请确定授权条款后补充 LICENSE，并同步更新说明。
