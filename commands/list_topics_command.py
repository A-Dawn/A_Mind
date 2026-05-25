"""
查看话题列表命令
"""
from typing import Tuple

from maibot_sdk.compat import BaseCommand, ComponentInfo, ComponentType, CommandInfo

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
try:
    from ..utils import get_global_db_manager
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from utils import get_global_db_manager

logger = get_logger(__name__)


class ListTopicsCommand(BaseCommand):
    """查看话题列表命令"""

    command_name = "amind_list"
    command_description = "查看所有话题列表"
    command_pattern = r"^/amind_list(\s+.+)?$"

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行查看话题列表命令"""
        try:
            # 获取话题列表
            topics = get_global_db_manager().list_topics()

            if not topics:
                await self.send_text("📭 暂无任何话题")
                return True, "查看话题列表", True

            # 构建回复消息
            message_lines = [f"📋 话题列表 (共{len(topics)}个):"]

            for topic in topics:
                status_emoji = {"active": "🟢", "paused": "🟡", "completed": "✅", "terminated": "❌"}.get(
                    topic.status, "❓"
                )

                visibility_emoji = "🔓" if topic.visibility == "public" else "🔒"

                message_lines.append(
                    f"{status_emoji}{visibility_emoji} [{topic.id}] {topic.title} - 参与度:{topic.engagement_score:.2f} 回复:{topic.reply_count}"
                )

            await self.send_text("\n".join(message_lines))
            return True, f"显示{len(topics)}个话题", True

        except Exception as e:
            logger.error(f"查看话题列表执行失败: {e}")
            return False, f"查看话题列表出错: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_list",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_list(\s+.+)?$",
            description="查看所有话题列表",
        )
