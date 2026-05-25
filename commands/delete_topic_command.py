"""
删除话题命令
"""
import re
from typing import Tuple

from maibot_sdk.compat import BaseCommand, ComponentInfo, ComponentType, CommandInfo
from ..core.permissions import require_permission

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
try:
    from ..utils import get_global_db_manager
except ImportError:
    # 直接导入时的备用方案
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from utils import get_global_db_manager

logger = get_logger(__name__)


class DeleteTopicCommand(BaseCommand):
    """删除话题命令"""

    command_name = "amind_delete"
    command_description = "删除指定话题"
    command_pattern = r"^/amind_delete\s+(\d+)$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行删除话题命令"""
        try:
            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text)
            if not match:
                return False, "命令格式错误，使用: /amind_delete <话题ID>", False

            topic_id = int(match.group(1))

            # 获取话题
            topic = get_global_db_manager().get_topic(topic_id)
            if not topic:
                return False, f"话题 {topic_id} 不存在", False

            # 检查权限（创建者、超级管理员或全局管理员模式）
            user_id = str(
                getattr(getattr(getattr(self.message, "message_info", None), "user_info", None), "user_id", "")
            )

            # 检查全局管理员模式
            global_admin_mode = self.get_config("permissions.global_admin_mode", False)
            if not global_admin_mode:
                # 非全局管理员模式，检查具体权限
                super_admins = self.get_config("permissions.super_admins", [])
                if topic.creator_id != user_id and user_id not in super_admins:
                    return False, "只有话题创建者或超级管理员可以删除话题", False

            # 删除话题
            success = get_global_db_manager().delete_topic(topic_id)
            if success:
                await self.send_text(f"✅ 话题删除成功！\n📝 标题：{topic.title}")
                return True, f"删除话题成功: {topic_id}", True
            else:
                return False, "话题删除失败，请稍后重试", False

        except ValueError:
            return False, "话题ID格式错误", False
        except Exception as e:
            logger.error(f"删除话题命令执行失败: {e}")
            return False, f"删除话题出错: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_delete",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_delete\s+(\d+)$",
            description="删除指定话题 - 用法: /amind_delete <话题ID>",
        )
