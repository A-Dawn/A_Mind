# -*- coding: utf-8 -*-
"""
A_Mind 日志管理器

提供灵活的日志控制机制，支持按模块、按级别、按功能控制日志输出。

优先级（从高到低）：
1. 模块级配置 (logging.modules.{category})
2. 全局级别 (logging.level)
3. 预设模式 (logging.preset)

设计原则：
- 隐式继承：未设置的配置自动继承上级
- 简洁优先：用户只需配置需要修改的部分
- 向后兼容：不配置时使用合理的默认值
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from src.common.logger import get_logger as base_get_logger


# 预设配置定义
PRESET_CONFIGS = {
    "minimal": {
        "level": "WARNING",
        "modules": {
            "services": "ERROR",
            "handlers": "WARNING",
            "commands": "ERROR",
            "core": "ERROR",
            "database": "ERROR",
        },
        "features": {
            "show_search_results": False,
            "show_llm_prompts": False,
            "show_topic_matching": False,
            "show_initiation_workflow": False,
            "show_performance_metrics": False,
        },
    },
    "normal": {
        "level": "INFO",
        "modules": {
            "services": "WARNING",
            "handlers": "INFO",
            "commands": "ERROR",
            "core": "WARNING",
            "database": "ERROR",
        },
        "features": {
            "show_search_results": False,
            "show_llm_prompts": False,
            "show_topic_matching": False,
            "show_initiation_workflow": False,
            "show_performance_metrics": False,
        },
    },
    "verbose": {
        "level": "INFO",
        "modules": {
            "services": "INFO",
            "handlers": "INFO",
            "commands": "INFO",
            "core": "INFO",
            "database": "WARNING",
        },
        "features": {
            "show_search_results": True,
            "show_llm_prompts": False,
            "show_topic_matching": True,
            "show_initiation_workflow": True,
            "show_performance_metrics": True,
        },
    },
    "debug": {
        "level": "DEBUG",
        "modules": {
            "services": "DEBUG",
            "handlers": "DEBUG",
            "commands": "DEBUG",
            "core": "DEBUG",
            "database": "DEBUG",
        },
        "features": {
            "show_search_results": True,
            "show_llm_prompts": True,
            "show_topic_matching": True,
            "show_initiation_workflow": True,
            "show_performance_metrics": True,
        },
    },
}


class AMindLogger:
    """A_Mind专用日志管理器

    提供灵活的日志控制，支持：
    - 预设模式（minimal/normal/verbose/debug）
    - 全局级别控制
    - 模块级别控制
    - 功能开关控制
    """

    # 日志级别映射
    LEVEL_MAP = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "OFF": logging.CRITICAL + 10,  # 完全禁用
        "INHERIT": None,  # 继承上级配置
    }

    # 模块分类映射
    MODULE_CATEGORIES = {
        # Services
        "information_retriever": "services",
        "brainstorm_generator": "services",
        "decision_selector": "services",
        "auto_sender": "services",
        "response_monitor": "services",

        # Handlers
        "auto_initiate_action": "handlers",
        "state_check_action": "handlers",
        "message_tracker": "handlers",
        "a_mind_start_handler": "handlers",

        # Commands
        "create_topic_command": "commands",
        "list_topics_command": "commands",
        "delete_topic_command": "commands",
        "update_topic_command": "commands",
        "initiate_command": "commands",
        "check_command": "commands",
        "debug_command": "commands",
        "help_command": "commands",
        "model_config_command": "commands",
        "visibility_command": "commands",
        "stream_management_command": "commands",

        # Core
        "config_manager": "core",
        "dependency_container": "core",
        "permissions": "core",
        "a_mind_plan_tick_task": "core",

        # Database
        "database_manager": "database",
        "topic_repository": "database",
        "reply_repository": "database",
    }

    def __init__(self, config_manager):
        """初始化日志管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config = config_manager
        self._loggers: Dict[str, logging.Logger] = {}
        self._handlers_cache: Dict[str, logging.Handler] = {}

    def get_logger(self, module_name: str) -> logging.Logger:
        """获取模块对应的logger

        Args:
            module_name: 模块名称（如 'auto_initiate_action'）
                          可以使用 __name__ 自动传入

        Returns:
            配置好的logger实例
        """
        # 标准化模块名（移除.py后缀）
        clean_name = module_name.replace(".py", "")

        if clean_name in self._loggers:
            return self._loggers[clean_name]

        # 创建新的logger - 使用唯一名称避免单例冲突
        # 格式: A_Mind.{module_name}
        unique_logger_name = f"A_Mind.{clean_name}"
        logger = logging.getLogger(unique_logger_name)

        # 确保logger不传播到父级（避免重复输出）
        logger.propagate = False

        # 配置logger
        self._configure_logger(logger, clean_name)

        # 缓存logger
        self._loggers[clean_name] = logger
        return logger

    def _configure_logger(self, logger: logging.Logger, module_name: str):
        """配置logger

        Args:
            logger: logger实例
            module_name: 模块名称
        """
        # 检查是否完全禁用日志
        if not self.config.get("logging.enabled", True):
            logger.setLevel(logging.CRITICAL + 10)
            return

        # 获取有效的日志级别
        level = self._get_effective_level(module_name)

        logger.setLevel(level)

        # 配置handler
        self._configure_handlers(logger, module_name)

    def _get_effective_level(self, module_name: str) -> int:
        """获取模块的有效日志级别

        优先级：模块配置 > 全局配置 > 预设配置

        Args:
            module_name: 模块名称

        Returns:
            日志级别（logging常量）
        """
        # 1. 获取模块类别
        category = self._get_module_category(module_name)

        # 2. 尝试获取模块级配置（最高优先级）
        module_level_str = self.config.get(f"logging.modules.{category}", "INHERIT")
        if module_level_str != "INHERIT":
            return self.LEVEL_MAP.get(module_level_str, logging.INFO)

        # 3. 尝试获取全局配置（中等优先级）
        global_level_str = self.config.get("logging.level", "INHERIT")
        if global_level_str != "INHERIT":
            return self.LEVEL_MAP.get(global_level_str, logging.INFO)

        # 4. 使用预设配置（最低优先级，作为兜底）
        preset = self.config.get("logging.preset", "normal")
        preset_config = PRESET_CONFIGS.get(preset, PRESET_CONFIGS["normal"])
        preset_module_level = preset_config["modules"].get(category, "INFO")
        return self.LEVEL_MAP.get(preset_module_level, logging.INFO)

    def _get_module_category(self, module_name: str) -> str:
        """获取模块所属类别

        Args:
            module_name: 模块名称

        Returns:
            类别名称 (services/handlers/commands/core/database/other)
        """
        # 移除文件扩展名
        clean_name = module_name.replace(".py", "")

        # 查找映射
        return self.MODULE_CATEGORIES.get(clean_name, "other")

    def _configure_handlers(self, logger: logging.Logger, module_name: str):
        """配置日志处理器

        Args:
            logger: logger实例
            module_name: 模块名称
        """
        # 清除现有handlers以避免重复
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 添加控制台handler
        console_handler = self._create_console_handler(module_name)
        logger.addHandler(console_handler)

        # 添加文件handler（如果启用）
        if self.config.get("logging.file_output.enabled", False):
            file_handler = self._create_file_handler(module_name)
            logger.addHandler(file_handler)

    def _create_console_handler(self, module_name: str) -> logging.StreamHandler:
        """创建控制台日志处理器

        Args:
            module_name: 模块名称

        Returns:
            控制台handler
        """
        handler = logging.StreamHandler(sys.stdout)

        # 设置格式
        formatter = self._create_formatter(module_name)
        handler.setFormatter(formatter)

        return handler

    def _create_file_handler(self, module_name: str) -> logging.Handler:
        """创建文件日志处理器

        Args:
            module_name: 模块名称

        Returns:
            文件handler
        """
        from logging.handlers import RotatingFileHandler

        # 获取文件配置
        log_path = self.config.get("logging.file_output.path", "logs/amind.log")
        max_size = self.config.get("logging.file_output.max_size_mb", 10) * 1024 * 1024
        backup_count = self.config.get("logging.file_output.backup_count", 5)

        # 确保日志目录存在
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 创建RotatingFileHandler
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count,
            encoding='utf-8'
        )

        # 文件始终使用详细格式
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] [%(levelname)s] [A_Mind] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)

        return handler

    def _create_formatter(self, module_name: str) -> logging.Formatter:
        """创建日志格式化器

        Args:
            module_name: 模块名称

        Returns:
            格式化器实例
        """
        # 获取格式配置
        show_timestamp = self.config.get("logging.format.show_timestamp", False)
        show_module = self.config.get("logging.format.show_module_name", False)
        compact = self.config.get("logging.format.compact_mode", True)

        # 构建格式字符串
        if compact:
            # 紧凑格式：[A_Mind] 消息内容
            fmt = "[A_Mind] %(message)s"
        else:
            # 详细格式
            parts = []
            if show_timestamp:
                parts.append("%(asctime)s")
            if show_module:
                parts.append("[%(name)s]")
            parts.append("[A_Mind] %(message)s")
            fmt = " ".join(parts)

        return logging.Formatter(fmt, datefmt="%H:%M:%S")

    def should_log(self, feature: str) -> bool:
        """检查是否应该记录某个特定功能的日志

        Args:
            feature: 功能名称（如 'show_search_results'）

        Returns:
            是否应该记录
        """
        return self.config.get(f"logging.features.{feature}", False)


# 全局日志管理器实例
_amind_logger_instance: Optional[AMindLogger] = None


def get_amind_logger() -> Optional[AMindLogger]:
    """获取全局AMind日志管理器实例

    Returns:
        AMindLogger实例或None（如果未初始化）
    """
    return _amind_logger_instance


def set_amind_logger(logger: AMindLogger):
    """设置全局AMind日志管理器实例

    Args:
        logger: AMindLogger实例
    """
    global _amind_logger_instance
    _amind_logger_instance = logger


def get_logger(module_name: str) -> logging.Logger:
    """获取配置好的logger（便捷函数）

    这是插件各模块应该使用的函数，替代直接使用 get_logger("A_Mind")

    Args:
        module_name: 模块名称，通常传入 __name__

    Returns:
        logger实例

    示例:
        >>> from core.amind_logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("这是一条日志")
    """
    # 尝试获取AMind日志管理器
    amid_logger = get_amind_logger()

    if amid_logger:
        # 使用AMind日志管理器获取配置好的logger
        return amid_logger.get_logger(module_name)
    else:
        # 如果日志管理器未初始化，使用默认logger
        # 这种情况通常发生在插件初始化早期
        return base_get_logger("A_Mind")
