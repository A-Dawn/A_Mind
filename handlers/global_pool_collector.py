"""
总控池消息采集处理器
"""

from maibot_sdk.compat import BaseEventHandler, EventType

try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

from ..services.global_pool_service import GlobalPoolService
from ..utils import get_global_db_manager

logger = get_logger(__name__)


class GlobalPoolCollectorEventHandler(BaseEventHandler):
    """采集白名单流消息到总控池"""

    event_type = EventType.ON_MESSAGE
    handler_name = "amind_global_pool_collector"
    handler_description = "总控池消息采集器（白名单流）"

    async def execute(self, message):
        try:
            if not self.get_config("global_pool.enabled", False):
                return True, True, None, None, None

            stream_id = str(getattr(message, "stream_id", "") or "")
            if not stream_id:
                return True, True, None, None, None

            service = GlobalPoolService(self.get_config, db_manager=get_global_db_manager())
            whitelist = service.get_whitelist_streams()
            if not whitelist or stream_id not in whitelist:
                return True, True, None, None, None

            content = getattr(message, "plain_text", getattr(message, "processed_plain_text", "")) or ""
            content = str(content).strip()
            if not content:
                return True, True, None, None, None

            # 过滤命令消息，避免把管理命令带入池子
            if content.startswith("/"):
                return True, True, None, None, None

            # 尝试过滤机器人自身消息
            if bool(getattr(message, "from_self", False)) or bool(getattr(message, "is_self", False)):
                return True, True, None, None, None

            user_info = getattr(getattr(message, "message_info", None), "user_info", None)
            user_id = str(getattr(user_info, "user_id", "") or "")
            message_id = str(getattr(getattr(message, "message_info", None), "message_id", "") or "")

            service.collect_message(
                stream_id=stream_id,
                message_id=message_id,
                user_id=user_id,
                content=content,
                role="user",
            )
            return True, True, None, None, None

        except Exception as e:
            logger.error(f"[A_Mind][GlobalPool] 采集器执行失败: {e}")
            return True, True, None, None, None
