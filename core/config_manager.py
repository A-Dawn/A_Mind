"""
配置管理器

统一管理插件的所有配置项
"""

from typing import Any, Optional


class ConfigManager:
    """配置管理器 - 提供统一配置访问接口"""

    def __init__(self, plugin_instance):
        """初始化配置管理器

        Args:
            plugin_instance: 插件实例，用于访问get_config方法
        """
        self.plugin = plugin_instance

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键，支持点号分隔的嵌套键，如 'llm.model_name'
            default: 默认值

        Returns:
            配置值或默认值
        """
        if callable(self.plugin):
            return self.plugin(key, default)
        return self.plugin.get_config(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔类型配置"""
        value = self.get(key, default)
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数类型配置"""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点类型配置"""
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_list(self, key: str, default: list = None) -> list:
        """获取列表类型配置"""
        if default is None:
            default = []
        value = self.get(key, default)
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            # 尝试解析字符串为列表
            import ast
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError):
                pass
        return default

    def get_dict(self, key: str, default: dict = None) -> dict:
        """获取字典类型配置"""
        if default is None:
            default = {}
        value = self.get(key, default)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            # 尝试解析字符串为字典
            import ast
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, SyntaxError):
                pass
        return default

    # 便捷方法 - 直接访问常用配置
    @property
    def enabled(self) -> bool:
        """插件是否启用"""
        return self.get_bool("plugin.enabled", False)

    @property
    def debug_mode(self) -> bool:
        """是否启用调试模式"""
        return self.get_bool("debug.enable_debug_mode", False)

    @property
    def llm_model(self) -> str:
        """LLM模型名称"""
        return self.get("llm.model_name", "utils")

    @property
    def max_active_topics(self) -> int:
        """最大同时活跃话题数"""
        return self.get_int("topic_management.max_active_topics", 5)

    @property
    def auto_initiate_enabled(self) -> bool:
        """自动发起是否启用"""
        return self.get_bool("plan1.enabled", False)

    @property
    def auto_initiate_interval(self) -> int:
        """自动发起检查间隔（秒）"""
        return self.get_int("plan1.tick_interval_seconds", 30)

    @property
    def auto_initiate_probability(self) -> float:
        """自动发起触发概率"""
        return self.get_float("plan1.trigger_probability", 0.02)

    def get_model_config(self, plan_name: str = None, service_name: str = None) -> dict:
        """获取模型配置，支持多层继承

        配置优先级：Plan特定 > 服务特定 > 全局默认

        Args:
            plan_name: Plan名称，如 'plan1'，None表示全局
            service_name: 服务名称，如 'brainstorm'，None表示通用配置

        Returns:
            dict: 包含 model_name, fallback_model_name, temperature, max_tokens 的配置字典
        """
        config = {}

        # 1. 获取全局默认配置
        config['model_name'] = self.get("llm.model_name", "replyer")
        config['fallback_model_name'] = self.get("llm.fallback_model_name", "replyer")
        config['temperature'] = self.get_float("llm.temperature", 0.7)
        config['max_tokens'] = self.get_int("llm.max_tokens", 1500)

        # 2. 如果指定了服务，覆盖服务级别配置
        if service_name:
            service_model = self.get(f"services.{service_name}.model_name", "")
            if service_model:
                config['model_name'] = service_model

            service_fallback = self.get(f"services.{service_name}.fallback_model_name", "")
            if service_fallback:
                config['fallback_model_name'] = service_fallback

            service_temp = self.get_float(f"services.{service_name}.temperature", None)
            if service_temp is not None:
                config['temperature'] = service_temp

            service_tokens = self.get_int(f"services.{service_name}.max_tokens", None)
            if service_tokens is not None:
                config['max_tokens'] = service_tokens

        # 3. 如果指定了plan，覆盖plan级别配置
        if plan_name:
            # Plan通用配置
            plan_model = self.get(f"{plan_name}.model_config.model_name", "")
            if plan_model:
                config['model_name'] = plan_model

            plan_fallback = self.get(f"{plan_name}.model_config.fallback_model_name", "")
            if plan_fallback:
                config['fallback_model_name'] = plan_fallback

            plan_temp = self.get_float(f"{plan_name}.model_config.temperature", None)
            if plan_temp is not None:
                config['temperature'] = plan_temp

            plan_tokens = self.get_int(f"{plan_name}.model_config.max_tokens", None)
            if plan_tokens is not None:
                config['max_tokens'] = plan_tokens

            # Plan特定服务配置（最高优先级）
            if service_name:
                plan_service_model = self.get(f"{plan_name}.services.{service_name}.model_name", "")
                if plan_service_model:
                    config['model_name'] = plan_service_model

                plan_service_fallback = self.get(f"{plan_name}.services.{service_name}.fallback_model_name", "")
                if plan_service_fallback:
                    config['fallback_model_name'] = plan_service_fallback

                plan_service_temp = self.get_float(f"{plan_name}.services.{service_name}.temperature", None)
                if plan_service_temp is not None:
                    config['temperature'] = plan_service_temp

                plan_service_tokens = self.get_int(f"{plan_name}.services.{service_name}.max_tokens", None)
                if plan_service_tokens is not None:
                    config['max_tokens'] = plan_service_tokens

        return config

    def get_available_models(self) -> list:
        """获取可用的模型名称列表

        Returns:
            list: 已知可用模型名称列表
        """
        # 直接返回已知的模型名称列表
        known_models = ["utils", "replyer", "planner"]
        try:
            from maibot_sdk.compat.apis.llm_api import get_available_models
            available_models = get_available_models()
            if available_models:
                # 返回动态获取的模型名称
                return list(available_models.keys())
        except Exception:
            # 如果无法获取，使用已知模型列表
            pass
        return known_models

