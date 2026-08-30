# TraceForce Coding Agent 路线图

> **Developed by zzz** · GitHub: https://github.com/zzz1-zzz2/zzzagent

TraceForce 当前版本已经是可运行的终端 Coding Agent。它的目标是让模型完成“读取项目 → 分析问题 → 修改文件 → 运行验证 → 根据结果修复 → 汇报证据”的真实软件工程闭环。后续工作围绕“让每次修改都可观察、可验证、可恢复”推进。本文件只描述尚未交付的能力，不代表路线图项目已经实现。

## 当前已交付

- 三包分层：模型边界、运行时核心、编码产品；
- 原生 `asyncio` Agent 循环和流式模型响应；
- `read`、`write`、`edit`、`bash` 工具及 workspace 边界；
- 参数校验、工具错误反馈、只读并发和写入保序；
- 权限确认、危险命令过滤和 bash 超时；
- 生命周期事件、Hook、Session 恢复/回退/分叉和上下文压缩；
- Skills、Subagents、Tasks、Extensions、Plugins、Memory 和 MCP；
- `traceforce` console script、当前目录启动、REPL 和一次性任务；
- 三个包的离线测试和独立 wheel 构建；
- Textual 全屏 TUI：对话流、可选中复制的对话和工具详情、可折叠/关闭的工具卡片、异步权限确认、任务取消和 Session 命令；内置 bash 已采用非交互 stdin、环境变量和 Unix 进程组清理；

## 下一阶段：可观察的交付闭环

### P0：Textual TUI

- [x] 在产品层增加 Textual 全屏界面；
- [x] 将现有事件流映射为状态栏、对话区、输入区和工具卡片；
- [x] 展示工具名称、参数摘要、耗时、状态和截断结果；
- [x] 支持权限确认、任务中止、Session 新建和恢复；
- [x] 对话和工具详情支持选择复制，工具卡片支持折叠、详情复制和关闭；
- [x] 内置 bash 使用 EOF stdin、非交互环境变量、超时处理和 Unix 进程组清理；
- [x] 保留现有纯终端模式，TUI 只作为 runtime 事件消费者。

### P1：结构化证据

- [ ] 引入 typed trajectory，统一记录模型请求、工具调用、工具结果和验证动作；
- [ ] 实现 `WorkspaceChangeTracker`，区分 Agent 修改、用户修改和外部命令产生的变化；
- [ ] 将测试、构建和 lint 结果作为结构化 evidence 暴露给产品层；
- [ ] 增加 `traceforce check`，检查 workspace、Session 和最近任务的验证证据；
- [ ] 为失败任务提供可复制的恢复摘要和诊断信息。

### P2：可靠性与发布

- [ ] 完整交互式 PTY 终端转发；
- [ ] 任意第三方同步工具的强制终止；
- [ ] 补充跨平台 smoke tests；
- [ ] 完善 wheel 元数据、版本策略、发布检查和 release automation；
- [ ] 在 API 稳定后再考虑 PyPI 发布。

## 约束

后续实现必须保持：

1. 不引入现成 Agent 编排框架或 Agent SDK；
2. 不绕过 workspace 边界、权限 Hook 和凭据保护；
3. 不把流式半成品或未验证的修改描述为完成结果；
4. 优先使用离线、确定性测试；
5. 新的持久化格式必须可恢复、可诊断，并明确兼容边界。
