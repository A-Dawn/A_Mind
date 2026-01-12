"""
创建话题命令
"""
import re
from typing import Tuple

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo
from ..core.permissions import require_permission

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
try:
    from ..models.topic import Topic
    from ..utils import get_global_db_manager
except ImportError:
    # 直接导入时的备用方案
    import sys
    from pathlib import Path
    # 添加插件路径到sys.path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from models.topic import Topic
    from utils import get_global_db_manager

logger = get_logger(__name__)


class CreateTopicCommand(BaseCommand):
    """创建话题命令"""

    command_name = "amind_create"
    command_description = "创建新话题"
    command_pattern = r"^/amind_create\s+(.+?)\s+(.+)$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行创建话题命令"""
        try:
            logger.info(f"[A_Mind] CreateTopicCommand 执行开始，消息内容: {getattr(self, 'message', 'No message')}")

            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            logger.info(f"[A_Mind] 消息文本: {message_text}")

            match = re.match(self.command_pattern, message_text)
            if not match:
                logger.info(f"[A_Mind] 命令格式不匹配: {message_text}")
                return False, "命令格式错误，使用: /amind_create <标题> <描述>", False

            logger.info(f"[A_Mind] 命令参数解析成功: {match.groups()}")

            title = match.group(1).strip()
            description = match.group(2).strip()

            if len(title) > 100:
                return False, "话题标题过长（最多100字符）", False

            if len(description) > 500:
                return False, "话题描述过长（最多500字符）", False

            # 创建话题对象
            user_info = getattr(getattr(self.message, "message_info", None), "user_info", None)
            creator_id = getattr(user_info, "user_id", "unknown_user") if user_info else "unknown_user"
            creator_name = getattr(user_info, "user_nickname", "未知用户") if user_info else "未知用户"

            # 获取当前聊天流ID，自动绑定到创建时的聊天流
            current_stream_id = getattr(getattr(self.message, "chat_stream", None), "stream_id", None)

            topic = Topic(
                title=title,
                description=description,
                creator_id=str(creator_id),
                creator_name=str(creator_name),
                status="active",
                priority=1,
                visibility="public",
                stream_ids=[current_stream_id] if current_stream_id else [],
            )

            # 保存到数据库
            topic_id = get_global_db_manager().create_topic(topic)
            if topic_id:
                await self.send_text(f"✅ 话题创建成功！\n📝 标题：{title}\n📋 描述：{description}\n🆔 ID：{topic_id}")
                return True, f"创建话题成功: {title}", True
            else:
                return False, "话题创建失败，请稍后重试", False

        except Exception as e:
            logger.error(f"创建话题命令执行失败: {e}")
            return False, f"创建话题出错: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_create",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_create\s+(.+?)\s+(.+)$",
            description="创建新话题 - 用法: /amind_create <标题> <描述>",
        )
