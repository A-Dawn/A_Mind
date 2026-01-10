"""
话题可见性管理命令
"""
import re
from typing import Tuple

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo
from src.common.logger import get_logger
from ..core.permissions import require_permission
try:
    from ..utils import get_global_db_manager
except ImportError:
    # 直接导入时使用绝对导入
    from plugins.A_Mind.utils import get_global_db_manager

logger = get_logger("A_Mind")


class VisibilityCommand(BaseCommand):
    """话题可见性管理命令"""

    command_name = "amind_visibility"
    command_description = "管理话题可见性设置"
    command_pattern = r"^/amind_visibility\s+(\d+)\s+(public|private)(?:\s+(.+))?$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行可见性设置命令"""
        try:
            logger.info("[A_Mind] VisibilityCommand 执行开始")

            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            logger.info(f"[A_Mind] 消息文本: {message_text}")

            match = re.match(self.command_pattern, message_text)
            if not match:
                logger.info("[A_Mind] 命令格式不匹配")
                return False, "命令格式错误，使用: /amind_visibility <话题ID> <public|private> [用户列表]", False

            topic_id = int(match.group(1))
            visibility = match.group(2)
            user_list_str = match.group(3)

            # 检查强制可见性设置
            force_visibility = self.get_config("topic_management.force_visibility", "")
            if force_visibility and force_visibility != visibility:
                return False, f"系统配置强制所有话题为{force_visibility}模式，无法修改", False

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
                    return False, "只有话题创建者或超级管理员可以修改可见性", False

            # 处理用户列表
            allowed_users = []
            if visibility == "private" and user_list_str:
                # 解析用户列表（用逗号或空格分隔）
                allowed_users = [u.strip() for u in re.split(r"[,\s]+", user_list_str) if u.strip()]
                if not allowed_users:
                    return False, "私有模式必须指定至少一个允许的用户", False
            elif visibility == "private" and not user_list_str:
                # 私有模式但未指定用户，默认为创建者
                allowed_users = [topic.creator_id]

            # 更新话题可见性
            updates = {"visibility": visibility, "allowed_users": allowed_users}

            success = get_global_db_manager().update_topic(topic_id, updates)
            if success:
                visibility_desc = "公开" if visibility == "public" else "私有"
                user_list_desc = f" (允许用户: {', '.join(allowed_users)})" if allowed_users else ""
                await self.send_text(
                    f"✅ 话题可见性设置成功！\n📝 话题：{topic.title}\n🔒 可见性：{visibility_desc}{user_list_desc}"
                )
                return True, f"设置话题可见性成功: {topic_id} -> {visibility}", True
            else:
                return False, "话题可见性设置失败，请稍后重试", False

        except ValueError:
            return False, "话题ID格式错误", False
        except Exception as e:
            logger.error(f"可见性设置执行失败: {e}")
            return False, f"可见性设置出错: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_visibility",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_visibility\s+(\d+)\s+(public|private)(?:\s+(.+))?$",
            description="设置话题可见性 (public=公开, private=私有) - 用法: /amind_visibility <话题ID> <public|private> [用户列表]",
        )
