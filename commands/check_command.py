"""
手动状态检查命令
"""
import re
import time
from typing import Tuple

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo
from src.common.logger import get_logger
from ..core.permissions import require_permission
try:
    from ..utils import get_global_db_manager
    from ..handlers.state_check_action import StateCheckAction
except ImportError:
    # 直接导入时使用绝对导入
    from plugins.A_Mind.utils import get_global_db_manager
    from plugins.A_Mind.handlers.state_check_action import StateCheckAction

logger = get_logger("A_mind")


class CheckCommand(BaseCommand):
    """手动状态检查命令"""

    command_name = "amind_check"
    command_description = "手动触发话题状态检查"
    command_pattern = r"^/amind_check\s+(\d+)$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行状态检查命令"""
        try:
            logger.info("[A_mind] CheckCommand 执行开始")
            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text)
            if not match:
                return False, "命令格式错误，使用 /amind_check <话题ID>", False

            topic_id = int(match.group(1))

            # 获取话题
            topic = get_global_db_manager().get_topic(topic_id)
            if not topic:
                return False, f"话题 {topic_id} 不存在", False

            # 创建状态检查Action并执□?            # 为StateCheckAction提供必需的初始化参数  # TODO: U+FFFD 替换点需人工核对
            action_data = {"check_type": "manual", "topic_ids": [topic_id]}
            action_reasoning = f"手动状态检查命令，话题ID: {topic_id}"
            cycle_timers = {}
            thinking_id = f"check_{topic_id}_{int(time.time())}"

            # 获取chat_stream
            chat_stream = getattr(self.message, "chat_stream", None)
            if not chat_stream:
                return False, "无法获取聊天流信息", False

            # 创建 action_message 适配器，将 MessageRecv 转换为 BaseAction 期望的格式
            class _ActionMessageAdapter:
                def __init__(self, message_recv):
                    self.message_recv = message_recv

                @property
                def chat_info(self):
                    # 创建 chat_info 对象
                    class _ChatInfo:
                        def __init__(self, message_info):
                            self.group_info = message_info.group_info
                    return _ChatInfo(self.message_recv.message_info)

                @property
                def user_info(self):
                    return self.message_recv.message_info.user_info

            action_message_adapter = _ActionMessageAdapter(self.message)

            check_action = StateCheckAction(
                action_data=action_data,
                action_reasoning=action_reasoning,
                cycle_timers=cycle_timers,
                thinking_id=thinking_id,
                chat_stream=chat_stream,
                action_message=action_message_adapter,
            )

            # 执行状态检查
            success, message = await check_action.execute()

            if success:
                await self.send_text(f"✅ 状态检查完成！\n📝 话题：{topic.title}\n📊 结果：{message}")
                return True, f"手动检查话题状态 {topic_id}", True
            else:
                return False, f"状态检查失败 {message}", False

        except ValueError:
            return False, "话题ID格式错误", False
        except Exception as e:
            logger.error(f"状态检查命令执行失败 {e}")
            return False, f"状态检查命令出错 {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_check",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_check\s+(\d+)$",
            description="手动触发话题状态检查 - 用法: /amind_check <话题ID>",
        )
