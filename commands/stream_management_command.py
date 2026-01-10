"""
聊天流管理命令"""
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

logger = get_logger("A_mind")


class StreamManagementCommand(BaseCommand):
    """聊天流管理命令 - 支持话题绑定和状态管理"""

    command_name = "amind_stream"
    command_description = "管理话题的聊天流绑定和状态"
    command_pattern = r"^/amind_stream\s+(\w+)\s+(\d+)(?:\s+(.+))?$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行聊天流管理命令"""
        try:
            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text)
            if not match:
                return False, "命令格式错误，使用 /amind_stream <操作> <话题ID> [参数]\n操作: bind/unbind/status", False

            operation = match.group(1).lower()
            topic_id = int(match.group(2))
            param = match.group(3) if match.group(3) else ""

            # 获取当前聊天流ID
            current_stream_id = getattr(getattr(self.message, "chat_stream", None), "stream_id", None)
            if not current_stream_id:
                return False, "无法获取当前聊天流信息", False

            # 获取话题
            topic = get_global_db_manager().get_topic(topic_id)
            if not topic:
                return False, f"话题 {topic_id} 不存在", False

            # 检查权限
            user_id = str(
                getattr(getattr(getattr(self.message, "message_info", None), "user_info", None), "user_id", "")
            )
            global_admin_mode = self.get_config("permissions.global_admin_mode", False)
            if not global_admin_mode:
                super_admins = self.get_config("permissions.super_admins", [])
                if topic.creator_id != user_id and user_id not in super_admins:
                    return False, "只有话题创建者或超级管理员可以管理聊天流绑定", False

            # 执行操作
            if operation == "bind":
                # 绑定当前聊天流到话题
                if current_stream_id in topic.stream_ids:
                    return False, f"话题 {topic_id} 已经绑定到当前聊天流", False

                new_stream_ids = topic.stream_ids + [current_stream_id]
                success = get_global_db_manager().update_topic(topic_id, {"stream_ids": new_stream_ids})

                if success:
                    # 创建聊天流状态记录                    get_global_db_manager()._create_topic_stream_state(topic_id, current_stream_id)
                    await self.send_text(f"✅绑定成功！\n📝 话题：{topic.title}\n🏷️聊天流：{current_stream_id}")
                    return True, f"绑定聊天流成功 {topic_id} -> {current_stream_id}", True
                else:
                    return False, "绑定失败，请稍后重试", False

            elif operation == "unbind":
                # 从话题解绑当前聊天流
                if current_stream_id not in topic.stream_ids:
                    return False, f"话题 {topic_id} 未绑定到当前聊天流", False

                new_stream_ids = [sid for sid in topic.stream_ids if sid != current_stream_id]
                success = get_global_db_manager().update_topic(topic_id, {"stream_ids": new_stream_ids})

                if success:
                    await self.send_text(f"✅解绑成功！\n📝 话题：{topic.title}\n🏷️聊天流：{current_stream_id}")
                    return True, f"解绑聊天流成功 {topic_id} -> {current_stream_id}", True
                else:
                    return False, "解绑失败，请稍后重试", False

            elif operation == "status":
                # 查看当前聊天流的绑定状态                
                stream_state = get_global_db_manager().get_topic_stream_state(topic_id, current_stream_id)
                if not stream_state:
                    status_info = "未绑定"
                else:
                    status_info = f"状态: {stream_state.status}"

                await self.send_text(f"📊 聊天流状态\n📝 话题：{topic.title}\n🏷️聊天流：{current_stream_id}\n📈 {status_info}")
                return True, f"查看状态成功 {topic_id} -> {current_stream_id}", True

            elif operation == "pause":
                # 暂停当前聊天流中的话题
                if current_stream_id not in topic.stream_ids:
                    return False, f"话题 {topic_id} 未绑定到当前聊天流", False

                stream_updates = {"status": "paused"}
                success = get_global_db_manager().update_topic_stream_state(topic_id, current_stream_id, stream_updates)

                if success:
                    await self.send_text(f"⏸️ 暂停成功！\n📝 话题：{topic.title}\n🏷️聊天流：{current_stream_id}")
                    return True, f"暂停话题成功: {topic_id} -> {current_stream_id}", True
                else:
                    return False, "暂停失败，请稍后重试", False

            elif operation == "resume":
                # 恢复当前聊天流中的话题
                if current_stream_id not in topic.stream_ids:
                    return False, f"话题 {topic_id} 未绑定到当前聊天流", False

                stream_updates = {"status": "active"}
                success = get_global_db_manager().update_topic_stream_state(topic_id, current_stream_id, stream_updates)

                if success:
                    await self.send_text(f"▶️ 恢复成功！\n📝 话题：{topic.title}\n🏷️聊天流：{current_stream_id}")
                    return True, f"恢复话题成功: {topic_id} -> {current_stream_id}", True
                else:
                    return False, "恢复失败，请稍后重试", False

            elif operation == "terminate":
                # 终止当前聊天流中的话题
                if current_stream_id not in topic.stream_ids:
                    return False, f"话题 {topic_id} 未绑定到当前聊天流", False

                stream_updates = {"status": "terminated"}
                success = get_global_db_manager().update_topic_stream_state(topic_id, current_stream_id, stream_updates)

                if success:
                    await self.send_text(f"🛑 终止成功！\n📝 话题：{topic.title}\n🏷️聊天流：{current_stream_id}")
                    return True, f"终止话题成功: {topic_id} -> {current_stream_id}", True
                else:
                    return False, "终止失败，请稍后重试", False

            else:
                return False, f"未知操作: {operation}，支持 bind/unbind/status/pause/resume/terminate", False

        except ValueError:
            return False, "话题ID格式错误", False
        except Exception as e:
            logger.error(f"聊天流管理命令执行异常 {e}")
            return False, f"执行异常: {str(e)}", False

    @classmethod
    def get_command_info(cls):
        return CommandInfo(
            name="amind_stream",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_stream\s+(\w+)\s+(\d+)(?:\s+(.+))?$",
            description="管理话题的聊天流绑定和状态 - 用法: /amind_stream <操作> <话题ID>\n操作: bind(绑定)/unbind(解绑)/status(状态)/pause(暂停)/resume(恢复)/terminate(终止)",
        )
