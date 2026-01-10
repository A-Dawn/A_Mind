"""
模型配置查看命令
"""
from typing import Tuple

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo
from src.common.logger import get_logger

try:
    from ..core.config_manager import ConfigManager
except ImportError:
    from plugins.A_Mind.core.config_manager import ConfigManager

logger = get_logger("A_Mind")


class ModelConfigCommand(BaseCommand):
    """模型配置查看命令"""

    command_name = "amind_models"
    command_description = "查看可用模型和当前配置"
    command_pattern = r"^/amind_models(\s+(plan|service|global|all))?$"

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行模型配置命令"""
        try:
            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            import re
            match = re.match(self.command_pattern, message_text)

            if not match:
                return False, "命令格式错误，使用: /amind_models [plan|service|global|all]", False

            scope = match.group(2) if match.group(2) else "all"

            # 获取配置管理器
            config_manager = ConfigManager(lambda key, default=None: self.get_config(key, default))

            # 构建响应文本
            response_text = "**🤖 A_Mind 模型配置**\n\n"

            # 显示可用模型
            available_models = config_manager.get_available_models()
            if available_models:
                response_text += f"**📋 可用模型 ({len(available_models)}个)**\n"
                for i, model in enumerate(available_models, 1):
                    response_text += f"{i}. `{model}`\n"
                response_text += "\n"
            else:
                response_text += "**⚠️ 无法获取可用模型列表**\n\n"

            # 根据scope显示不同层级的配置
            if scope in ["global", "all"]:
                response_text += self._format_global_config(config_manager)

            if scope in ["service", "all"]:
                response_text += self._format_service_config(config_manager)

            if scope in ["plan", "all"]:
                response_text += self._format_plan_config(config_manager)

            if scope == "all":
                response_text += "**💡 配置继承说明**\n"
                response_text += "配置优先级：Plan特定 > 服务特定 > 全局默认\n"
                response_text += "空值表示使用上级配置\n"

            await self.send_text(response_text)
            return True, f"显示{scope}模型配置", True

        except Exception as e:
            logger.error(f"模型配置命令执行失败: {e}")
            return False, f"模型配置命令出错: {str(e)}", False

    def _format_global_config(self, config_manager: ConfigManager) -> str:
        """格式化全局配置"""
        text = "**🌐 全局模型配置**\n"
        text += f"• 主模型: `{config_manager.get('llm.model_name', 'replyer')}`\n"
        text += f"• 备选模型: `{config_manager.get('llm.fallback_model_name', 'tool_use')}`\n"
        text += f"• 温度: `{config_manager.get_float('llm.temperature', 0.7)}`\n"
        text += f"• 最大token: `{config_manager.get_int('llm.max_tokens', 1500)}`\n\n"
        return text

    def _format_service_config(self, config_manager: ConfigManager) -> str:
        """格式化服务配置"""
        text = "**🔧 服务级别配置**\n"

        # 头脑风暴配置
        brainstorm_config = config_manager.get_model_config(None, 'brainstorm')
        text += "**🧠 头脑风暴**\n"
        text += f"• 主模型: `{brainstorm_config['model_name']}`\n"
        text += f"• 备选模型: `{brainstorm_config['fallback_model_name']}`\n"
        text += f"• 温度: `{brainstorm_config['temperature']}`\n"
        text += f"• 最大token: `{brainstorm_config['max_tokens']}`\n\n"

        # 决策选择配置
        decision_config = config_manager.get_model_config(None, 'decision')
        text += "**⚖️ 决策选择**\n"
        text += f"• 主模型: `{decision_config['model_name']}`\n"
        text += f"• 备选模型: `{decision_config['fallback_model_name']}`\n"
        text += f"• 温度: `{decision_config['temperature']}`\n"
        text += f"• 最大token: `{decision_config['max_tokens']}`\n\n"

        return text

    def _format_plan_config(self, config_manager: ConfigManager) -> str:
        """格式化Plan配置"""
        text = "**📋 Plan级别配置**\n"

        # 检查所有plan
        try:
            import toml
            import os
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.toml")
            if os.path.exists(config_path):
                config = toml.load(config_path)
                for key in config.keys():
                    if key.startswith('plan') and isinstance(config[key], dict):
                        text += self._format_single_plan_config(config_manager, key)
        except Exception:
            text += "⚠️ 无法读取Plan配置\n"

        return text

    def _format_single_plan_config(self, config_manager: ConfigManager, plan_name: str) -> str:
        """格式化单个Plan的配置"""
        text = f"**{plan_name.upper()}**\n"

        # Plan通用配置
        plan_config = config_manager.get_model_config(plan_name, None)
        text += f"• 通用主模型: `{plan_config['model_name']}`\n"
        text += f"• 通用备选模型: `{plan_config['fallback_model_name']}`\n"
        text += f"• 通用温度: `{plan_config['temperature']}`\n"
        text += f"• 通用最大token: `{plan_config['max_tokens']}`\n\n"

        # Plan服务配置
        brainstorm_plan_config = config_manager.get_model_config(plan_name, 'brainstorm')
        if (brainstorm_plan_config['model_name'] != plan_config['model_name'] or
            brainstorm_plan_config['temperature'] != plan_config['temperature']):
            text += f"• 头脑风暴主模型: `{brainstorm_plan_config['model_name']}`\n"
            text += f"• 头脑风暴温度: `{brainstorm_plan_config['temperature']}`\n"

        decision_plan_config = config_manager.get_model_config(plan_name, 'decision')
        if (decision_plan_config['model_name'] != plan_config['model_name'] or
            decision_plan_config['temperature'] != plan_config['temperature']):
            text += f"• 决策选择主模型: `{decision_plan_config['model_name']}`\n"
            text += f"• 决策选择温度: `{decision_plan_config['temperature']}`\n"

        text += "\n"
        return text

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_models",
            component_type=ComponentType.COMMAND,
            description="查看可用模型和当前配置",
            plugin_name="a_mind",
        )
