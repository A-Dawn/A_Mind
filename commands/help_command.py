"""
帮助命令
"""
from typing import Tuple

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

logger = get_logger(__name__)


class HelpCommand(BaseCommand):
    """帮助命令"""

    command_name = "amind_help"
    command_description = "显示所有可用命令"
    command_pattern = r"^/amind_help$"

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行帮助命令"""
        try:
            help_text = " **A_Mind 智能话题管理插件**\n\n"
            help_text += " **基础管理命令**\n"
            help_text += "• `/amind_create <标题> <描述>` - 创建新话题\n"
            help_text += "• `/amind_list` - 查看所有话题列表\n"
            help_text += "• `/amind_update <话题ID> title <新标题>` - 更新话题标题\n"
            help_text += "• `/amind_update <话题ID> desc <新描述>` - 更新话题描述\n"
            help_text += "• `/amind_delete <话题ID>` - 删除指定话题\n"
            help_text += "• `/amind_visibility <话题ID> <public|private> [用户列表]` - 设置话题可见性\n"
            help_text += "• `/amind_check <话题ID>` - 手动触发状态检查\n"
            help_text += "• `/amind_initiate [话题ID] [stream:聊天流配置]` - 手动触发话题自发起\n"
            help_text += "• `/amind_help` - 显示此帮助信息\n\n"

            help_text += " **调试命令**（仅限调试模式）\n"
            help_text += "• `/amind_debug show_state <话题ID>` - 显示话题内部状态\n"
            help_text += "• `/amind_debug force_create <标题> <描述>` - 强制创建话题\n"

            await self.send_text(help_text)
            return True, "显示帮助信息", True

        except Exception as e:
            logger.error(f"帮助命令执行失败: {e}")
            return False, f"帮助命令出错: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_help",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_help$",
            description="显示所有可用命令",
        )
