"""
核心组件包

提供核心组件的惰性导出，避免包初始化时触发循环导入。
"""

__all__ = [
    "ConfigManager",
    "DependencyContainer",
    "PermissionManager",
]


def __getattr__(name):
    if name == "ConfigManager":
        from .config_manager import ConfigManager

        return ConfigManager
    if name == "DependencyContainer":
        from .dependency_container import DependencyContainer

        return DependencyContainer
    if name == "PermissionManager":
        from .permissions import PermissionManager

        return PermissionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

