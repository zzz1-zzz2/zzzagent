"""extension 机制 —— 外部扩展加载（事件订阅 + 工具注册 + 命令）。"""

from traceforce_runtime.extensions.core import (
    CommandHandler,
    ExtensionAPI,
    ExtensionManager,
)

__all__ = ["ExtensionAPI", "ExtensionManager", "CommandHandler"]
