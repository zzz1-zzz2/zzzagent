# 任务 02：恢复 Blueprint middleware 顺序

TraceForce 当前运行在较旧版本的 `sanic` 项目 checkout 上。Blueprint middleware 按声明顺序注册；一个 Blueprint 周围的 request/response middleware 必须按照框架约定的语义执行。

请检查 Blueprint 注册流程、应用层 middleware registry 以及项目现有测试约定，定位顺序错误的原因。修复实现，使 Blueprint 声明的 middleware 在 request 和 response 两个阶段都按照预期顺序执行。修改应保持范围尽可能小，并兼容现有 API。请运行定向 Blueprint 测试，并根据需要执行其他本地检查验证行为。

不要复制 reference patch，也不要修改评测脚本。Agent 应通过阅读和推理完成修复，并在生成的项目 workspace 中留下最小、可维护的生产代码修改。
