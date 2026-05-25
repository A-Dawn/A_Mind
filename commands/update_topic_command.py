"""
更新话题命令
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
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from utils import get_global_db_manager

logger = get_logger(__name__)


class UpdateTopicCommand(BaseCommand):
    """更新话题命令"""

    command_name = "amind_update"
    command_description = "更新话题信息"
    command_pattern = r"^/amind_update\s+(\d+)\s+(title|desc)\s+(.+)$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行更新话题命令"""
        try:
            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text)
            if not match:
                return False, "命令格式错误，使用: /amind_update <话题ID> title <新标题> 或 /amind_update <话题ID> desc <新描述>", False

            topic_id = int(match.group(1))
            update_type = match.group(2)  # "title" 或 "desc"
            new_content = match.group(3).strip()

            # 验证内容长度
            if update_type == "title":
                if len(new_content) > 100:
                    return False, "话题标题过长（最多100字符）", False
                updates = {"title": new_content}
                field_name = "标题"
            else:  # desc
                if len(new_content) > 500:
                    return False, "话题描述过长（最多500字符）", False
                updates = {"description": new_content}
                field_name = "描述"

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
                    return False, "只有话题创建者或超级管理员可以修改话题", False

            # 更新话题
            success = get_global_db_manager().update_topic(topic_id, updates)
            if success:
                await self.send_text(f"✅ 话题{field_name}更新成功！\n📝 话题：{topic.title}\n{field_name}：{new_content}")
                return True, f"更新话题{field_name}成功: {topic_id}", True
            else:
                return False, "话题更新失败，请稍后重试", False

        except ValueError:
            return False, "话题ID格式错误", False
        except Exception as e:
            logger.error(f"更新话题命令执行失败: {e}")
            return False, f"更新话题出错: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_update",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_update\s+(\d+)\s+(title|desc)\s+(.+)$",
            description="更新话题信息 - 用法: /amind_update <话题ID> title <新标题> 或 /amind_update <话题ID> desc <新描述>",
        )
