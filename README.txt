TraceForce Coding Agent
=======================

面向真实软件工程任务的可验证编程智能体
Developed by zzz · GitHub: https://github.com/zzz1-zzz2/zzzagent

TraceForce 是由 zzz 独立开发的、面向真实软件工程任务的 Coding Agent。它不只是对话窗口，也不依赖现成的 Agent 框架或 Agent SDK，而是自己实现模型适配、工具调用循环、文件操作、命令执行、权限确认、上下文管理、会话持久化和验证反馈。

它的核心目标是让模型真正参与软件工程工作：读取项目 -> 分析问题 -> 修改文件 -> 运行验证 -> 根据结果修复 -> 汇报证据。

实现由三个独立 Python 包组成：traceforce-llm 负责 OpenAI、DeepSeek、Anthropic 及 OpenAI 兼容网关的统一模型接口；traceforce-runtime 负责 Agent 循环、工具注册、上下文、事件和 JSONL Session；traceforce 负责 Coding Agent、CLI 和 workspace 工具。evals/ 是独立验收层，只负责任务定义、workspace 准备、独立 verify 和可选证据，不复制 Agent loop；评测流程为 Prepare -> Baseline -> Run Agent -> Verify -> Collect Evidence -> Reset。

安装
----
环境要求：Python 3.11+、uv，以及一个兼容的模型 API。

在仓库中分别安装三个包：

  cd packages/traceforce-llm && uv sync
  cd ../traceforce-runtime && uv sync
  cd ../traceforce && uv sync

配置与运行
----------
复制 packages/traceforce/.env.example 到目标工作区的 .env，在本地填写模型配置。例如：

  TRACEFORCE_PROVIDER=openai
  TRACEFORCE_MODEL=your-model-name
  OPENAI_API_KEY=

也可以使用 DEEPSEEK_API_KEY、DEEPSEEK_MODEL、ANTHROPIC_API_KEY 等 Provider 专用变量。API key 只通过环境变量或未入库的 .env 提供，不写入仓库、README、Session、截图或视频。

在目标工作区执行一次任务：

  uv run --project /path/to/traceforce/packages/traceforce traceforce \
    --workspace /path/to/project \
    "读取项目，定位失败测试的原因，修改最小必要代码并运行测试验证"

省略任务文本可进入 REPL。默认启动工作区是当前目录；写入、编辑和 bash 命令默认需要人工确认，可在信任的工作区使用 --yes。Session 保存在工作区的 .traceforce/sessions/，可用 --session 恢复。

使用 --tui 可启动 Textual 全屏界面；界面提供 assistant 流式输出、可选中复制的对话与工具详情、可折叠/关闭的工具卡片、Allow/Deny 权限弹窗、任务取消和 Session 命令（/help、/session、/sessions、/clear、/mcp、/exit）。默认模式仍为纯终端 CLI。内置 bash 使用 EOF stdin 和非交互环境变量；需要交互输入的命令不会获得 TUI stdin，应使用 --yes、-y 或 --no-input 等非交互参数。

核心技术
--------
TraceForce 没有使用 LangChain、LlamaIndex、OpenAI Agents SDK、Claude Agent SDK、AutoGen、CrewAI 或其他现成 Agent 编排框架。模型厂商 SDK 只用于 API 连接，Agent 控制流由本项目实现。bash 不是操作系统级沙箱；当前内置 bash 是非交互工具，使用 EOF stdin、非交互环境变量、超时和 Unix 进程组清理。

Agent Loop 的基本流程是：

  用户输入 -> 生成上下文视图 -> 调用模型（支持 streaming）
  -> 解析 tool_calls -> 校验参数 -> 执行本地工具
  -> 将 ToolResult 写回消息 -> 继续循环
  -> 没有 tool call 时结束

循环同时具有语义终止条件和默认 30 次迭代的资源型兜底。每个工具调用都有结构化成功/失败结果；错误文本会作为 tool 消息反馈给模型，允许模型修正路径、参数或代码。文件工具严格检查 workspace 路径边界，read 只读，write/edit 受文件锁保护，bash 在 workspace 中运行且有危险命令过滤和超时处理。bash 当前不是操作系统级沙箱。

验证情况
--------
三个包均提供离线测试，使用 FakeLLM、Fake SDK 和临时工作区，不需要真实 API key。当前基线为 traceforce-llm 36 项、traceforce-runtime 228 项、traceforce 45 项，共 309 项测试；三个包均可独立执行 uv lock --check、pytest 和 uv build。

当前版本已提供 Textual 全屏 TUI：对话与工具详情可选中复制；工具卡片支持折叠、详情复制和关闭；bash 使用 EOF stdin、非交互环境变量、超时和 Unix 进程组清理。TUI 的 Ctrl+C 在无选区时取消任务，有选区时复制；终端剪贴板支持取决于 OSC52。仍未包含 typed trajectory、WorkspaceChangeTracker、traceforce check、完整交互式 PTY 终端转发、任意第三方同步工具的强制终止和 PyPI 发布自动化；这些能力在 ROADMAP.md 中列为后续工作。
