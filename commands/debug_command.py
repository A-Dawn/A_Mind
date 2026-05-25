"""
调试命令
"""
import re
import time
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
    from ..models.topic import Topic
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from utils import get_global_db_manager
    from models.topic import Topic

logger = get_logger(__name__)


class DebugCommand(BaseCommand):
    """调试命令"""

    command_name = "amind_debug"
    command_description = "调试功能命令"
    command_pattern = r"^/amind_debug\s+(.+)$"

    @require_permission("debug")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行调试命令"""
        try:
            # 检查调试模式是否启用
            if not self.get_config("debug.enable_debug_mode", False):
                return False, "调试模式未启用", False

            # 解析子命令
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text)
            if not match:
                return False, "调试命令格式错误", False

            sub_command = match.group(1).strip()
            parts = sub_command.split()
            command_type = parts[0] if parts else ""

            # 处理不同类型的调试命令
            if command_type == "show_state" and len(parts) >= 2:
                return await self._debug_show_state(parts[1])
            elif command_type == "force_create" and len(parts) >= 3:
                title = " ".join(parts[1:-1])
                description = parts[-1]
                return await self._debug_force_create(title, description)
            elif command_type == "list_all":
                return await self._debug_list_all()
            else:
                return False, f"未知调试命令: {command_type}", False

        except Exception as e:
            logger.error(f"调试命令执行失败: {e}")
            return False, f"调试命令执行出错: {str(e)}", False

    async def _debug_show_state(self, topic_id_str: str) -> Tuple[bool, str, bool]:
        """显示话题内部状态"""
        try:
            topic_id = int(topic_id_str)
            topic = get_global_db_manager().get_topic(topic_id)

            if not topic:
                await self.send_text(f"❌ 话题 {topic_id} 不存在")
                return False, f"话题不存在: {topic_id}", False

            # 构建状态信息
            state_info = f"🔍 话题 {topic_id} 内部状态:\n"
            state_info += f"📝 标题: {topic.title}\n"
            state_info += f"📋 描述: {topic.description}\n"
            state_info += f"👤 创建者: {topic.creator_name} ({topic.creator_id})\n"
            state_info += f"📊 状态: {topic.status}\n"
            state_info += f"🔒 可见性: {topic.visibility}\n"
            state_info += f"⭐ 优先级: {topic.priority}\n"
            state_info += f"💬 回复数: {topic.reply_count}\n"
            state_info += f"📈 参与度: {topic.engagement_score:.2f}\n"
            state_info += f"🔍 检查次数: {topic.check_count}\n"
            state_info += f"🚀 自发起次数: {topic.auto_initiate_count}\n"
            state_info += f"⏰ 创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(topic.created_at))}\n"
            state_info += f"🔄 最后活动: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(topic.last_activity)) if topic.last_activity else '无'}\n"

            await self.send_text(state_info)
            return True, f"显示话题状态: {topic_id}", True

        except ValueError:
            return False, "话题ID格式错误", False

    async def _debug_force_create(self, title: str, description: str) -> Tuple[bool, str, bool]:
        """强制创建话题（跳过权限检查）"""
        try:
            if len(title) > 100 or len(description) > 500:
                return False, "标题或描述过长", False

            # 创建话题对象（使用调试用户作为创建者）
            topic = Topic(
                title=title,
                description=description,
                creator_id="debug_user",
                creator_name="调试用户",
                status="active",
                priority=1,
                visibility="public",
            )

            # 保存到数据库
            topic_id = get_global_db_manager().create_topic(topic)
            if topic_id:
                await self.send_text(
                    f"🔧 [调试] 强制创建话题成功！\n📝 标题：{title}\n📋 描述：{description}\n🆔 ID：{topic_id}"
                )
                return True, f"调试创建话题成功: {title}", True
            else:
                return False, "调试创建话题失败", False

        except Exception as e:
            logger.error(f"调试创建话题失败: {e}")
            return False, "调试创建话题出错", False

    async def _debug_list_all(self) -> Tuple[bool, str, bool]:
        """列出所有话题（包括调试信息）"""
        try:
            topics = get_global_db_manager().list_topics()

            if not topics:
                await self.send_text("🔧 [调试] 数据库中无任何话题")
                return True, "调试列出所有话题", True

            message_lines = [f"🔧 [调试] 所有话题 ({len(topics)}个):"]

            for topic in topics:
                status_emoji = {"active": "🟢", "paused": "🟡", "completed": "✅", "terminated": "❌"}.get(
                    topic.status, "❓"
                )

                message_lines.append(
                    f"{status_emoji} [{topic.id}] {topic.title} - 参与度:{topic.engagement_score:.2f} 回复:{topic.reply_count}"
                )

            await self.send_text("\n".join(message_lines))
            return True, f"调试显示所有{len(topics)}个话题", True

        except Exception as e:
            logger.error(f"调试列出所有话题失败: {e}")
            return False, "调试列出话题出错", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_debug",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_debug\s+(.+)$",
            description="调试功能命令 - 仅限调试模式",
        )
