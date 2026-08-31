# 任务 03：从零创建 DevBoard 前端

请从一个空 workspace 开始，为需要快速查看项目健康状况的开发者创建一个小型、完整且有打磨感的 DevBoard 前端。

使用现代 React + Vite 方案，提供 package manifest 和生产构建脚本。页面不应只是 placeholder，而应表达清晰的产品概念：包含明确的 dashboard 标题、项目或 repository 的整体健康状态、实用的状态信息，以及便于快速浏览的布局。请保持视觉系统一致，并确保桌面端和窄屏视口都能正常使用。

生成的 workspace 必须能够通过 package manager 独立运行。请安装 manifest 中声明的依赖，执行生产构建，并在报告完成前通过浏览器或等效的 UI 预览检查页面。不要修改评测脚本，也不要添加 workspace manifest 未声明的依赖。

独立 verifier 只检查机器可验证的契约：`package.json`、build script 和成功的 production build。视觉质量和可用性属于人工验收证据，shell 脚本无法完整判断。
