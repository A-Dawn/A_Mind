"""
手动触发话题自发起命令
"""
import re
import time
from typing import Tuple, Optional

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo
from ..core.permissions import require_permission

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
try:
    from ..utils import get_global_db_manager
    from ..models.topic import Topic
    from ..handlers.auto_initiate_action import AutoInitiateAction
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from utils import get_global_db_manager
    from models.topic import Topic
    from handlers.auto_initiate_action import AutoInitiateAction

logger = get_logger(__name__)


class InitiateCommand(BaseCommand):
    """手动触发话题自发起命令"""

    command_name = "amind_initiate"
    command_description = "手动触发话题自发起"
    command_pattern = r"^/amind_initiate(\s+(\d+))?(?:\s+stream:([^\s]+))?$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        """执行自发起命令"""
        try:
            logger.info("[A_Mind] InitiateCommand 执行开始")

            # 解析命令参数
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text)
            if not match:
                return False, "命令格式错误，使用: /amind_initiate [话题ID] [stream:聊天流配置]", False

            topic_id_str = match.group(2) if match.group(2) else None
            stream_config_str = match.group(3) if match.group(3) else None

            if topic_id_str:
                # 指定话题ID的自发起
                try:
                    topic_id = int(topic_id_str)
                    # 获取话题
                    topic = get_global_db_manager().get_topic(topic_id)
                    if not topic:
                        return False, f"话题 {topic_id} 不存在", False

                    # 检查话题状态
                    if topic.status not in ["active", "paused"]:
                        return False, f"话题 {topic_id} 状态为 {topic.status}，无法自发起", False

                    # 执行单个话题的自发起
                    success = await self._execute_topic_initiation(topic, stream_config_str)
                    if success:
                        stream_info = f"\n🎯 聊天流：{stream_config_str}" if stream_config_str else ""
                        await self.send_text(f"✅ 自发起完成！\n📝 话题：{topic.title}\n🆔 ID：{topic_id}{stream_info}")
                        return True, f"手动自发起话题: {topic_id}", True
                    else:
                        return False, f"自发起失败: 话题 {topic_id}", False

                except ValueError:
                    return False, "话题ID格式错误", False
            else:
                # 自动选择话题进行自发起
                success, message = await self._execute_auto_initiation()

                if success:
                    await self.send_text(f"✅ 自动自发起完成！\n📊 结果：{message}")
                    return True, "自动选择话题进行自发起", True
                else:
                    return False, f"自动自发起失败: {message}", False

        except Exception as e:
            logger.error(f"自发起命令执行失败: {e}")
            return False, f"自发起命令出错: {str(e)}", False

    async def _execute_topic_initiation(self, topic: Topic, stream_config: Optional[str] = None) -> bool:
        """执行单个话题的自发起"""
        try:
            logger.info(f"[A_Mind] 开始执行话题 '{topic.title}' 的自发起")

            # 创建 AutoInitiateAction 实例来执行完整的工作流
            # 创建 action_message 适配器
            class _ActionMessageAdapter:
                def __init__(self, message_recv):
                    self.message_recv = message_recv

                @property
                def chat_info(self):
                    class _ChatInfo:
                        def __init__(self, message_info):
                            self.group_info = message_info.group_info
                    return _ChatInfo(self.message_recv.message_info)

                @property
                def user_info(self):
                    return self.message_recv.message_info.user_info

            action_message_adapter = _ActionMessageAdapter(self.message)

            # 创建 AutoInitiateAction 实例
            auto_initiate_action = AutoInitiateAction(
                action_data={"initiate_type": "manual", "target_topic_id": topic.id},
                action_reasoning=f"手动自发起命令，话题ID: {topic.id}",
                cycle_timers={},
                thinking_id=f"manual_initiate_{topic.id}_{int(time.time())}",
                chat_stream=self.message.chat_stream,
                action_message=action_message_adapter,
            )

            # 如果指定了stream_config，进行验证并临时覆盖默认配置
            if stream_config:
                # 验证stream_config格式
                if not self._validate_stream_config(stream_config):
                    return False

                logger.info(f"[A_Mind] 使用指定的聊天流配置: {stream_config}")
                # 创建一个临时配置管理器来覆盖默认配置
                original_get_config = auto_initiate_action.get_config

                def custom_get_config(key, default=None):
                    if key == "auto_initiate.default_stream_config":
                        return stream_config
                    return original_get_config(key, default)

                auto_initiate_action.get_config = custom_get_config

            # 设置 message 属性，确保 _get_target_stream_id 能正确工作
            auto_initiate_action.message = self._build_manual_initiate_message(stream_config)

            # 手动指定目标聊天流（如果当前消息的stream_id无效）
            target_stream_id = self._get_target_stream_for_manual_initiate(auto_initiate_action)
            if target_stream_id:
                logger.info(f"[A_Mind] 手动自发起将发送到聊天流: {target_stream_id}")
            else:
                logger.warning("[A_Mind] 无法确定手动自发起的目标聊天流，将依赖AutoInitiateAction的逻辑")

            # 设置依赖注入容器
            try:
                from ..plugin import _plugin_instance
                if _plugin_instance and hasattr(_plugin_instance, 'container'):
                    auto_initiate_action.container = _plugin_instance.container
                else:
                    # 设置基本配置管理器
                    class ConfigManager:
                        def __init__(self, get_config_func):
                            self._get_config = get_config_func

                        def get(self, key, default=None):
                            return self._get_config(key, default)

                        def get_model_config(self, plan_name=None, service_name=None):
                            """获取模型配置"""
                            return {
                                "model_name": self.get("llm.model_name", "tool_use"),
                                "fallback_model_name": self.get("llm.fallback_model_name", "tool_use"),
                                "temperature": self.get("llm.temperature", 0.7),
                                "max_tokens": self.get("llm.max_tokens", 1500),
                            }

                    auto_initiate_action.config_manager = ConfigManager(self.get_config)
            except Exception:
                pass  # 使用默认配置

            # 执行完整的工作流
            success = await auto_initiate_action._execute_initiation_workflow(topic)

            if success:
                # 更新话题的自发起统计（在工作流执行成功后）
                updates = {
                    "auto_initiate_count": topic.auto_initiate_count + 1,
                    "last_auto_initiate_at": time.time(),
                    "status": "active",  # 重新激活话题
                }
                get_global_db_manager().update_topic(topic.id, updates)

                logger.info(f"[A_Mind] 话题 '{topic.title}' 自发起工作流完成")
                return True
            else:
                logger.warning(f"[A_Mind] 话题 '{topic.title}' 自发起工作流失败")
                return False

        except Exception as e:
            logger.error(f"执行单个话题自发起失败: {e}")
            return False

    def _build_manual_initiate_message(self, stream_config: Optional[str] = None):
        """Build the message object used by AutoInitiateAction.

        A manual `stream:` override must win over the command message stream,
        because AutoInitiateAction reads `message.chat_stream` first.
        """
        if not stream_config:
            return self.message

        class _ChatStreamOverride:
            def __init__(self, stream_id: str):
                self.stream_id = stream_id
                self.session_id = stream_id

        class _MessageWithStreamOverride:
            def __init__(self, original_message, stream_id: str):
                self._original_message = original_message
                self.chat_stream = _ChatStreamOverride(stream_id)
                self.stream_id = stream_id
                self.session_id = stream_id

            def __getattr__(self, item):
                return getattr(self._original_message, item)

        return _MessageWithStreamOverride(self.message, stream_config)

    async def _execute_auto_initiation(self) -> Tuple[bool, str]:
        """执行自动选择话题的自发起"""
        try:
            # 获取活跃话题
            active_topics = get_global_db_manager().list_topics("active")

            if not active_topics:
                return False, "没有活跃的话题可以自发起"

            # 选择参与度最高的话题
            best_topic = max(active_topics, key=lambda t: t.engagement_score or 0.0)

            # 执行自发起
            success = await self._execute_topic_initiation(best_topic)

            if success:
                return True, f"选择话题 '{best_topic.title}' 进行自发起"
            else:
                return False, f"自发起失败: 话题 {best_topic.id}"

        except Exception as e:
            logger.error(f"执行自动自发起失败: {e}")
            return False, f"自动自发起出错: {str(e)}"

    def _get_target_stream_for_manual_initiate(self, auto_initiate_action) -> Optional[str]:
        """为手动自发起获取目标聊天流（增强版本）"""
        try:
            # 优先：使用命令消息的聊天流
            if hasattr(self.message, 'chat_stream') and self.message.chat_stream:
                stream_id = getattr(self.message.chat_stream, 'stream_id', None)
                if stream_id:
                    logger.debug(f"[A_Mind] 使用命令消息聊天流: {stream_id}")
                    return stream_id

            # 回退：使用配置的默认手动自发起聊天流
            default_config = str(self.get_config("auto_initiate.default_stream_config", "")).strip()
            if default_config:
                stream_id = auto_initiate_action._parse_stream_config_to_stream_id(default_config)
                if stream_id:
                    logger.debug(f"[A_Mind] 使用默认手动自发起聊天流: {stream_id}")
                    return stream_id

            # 最后回退：使用Plan-1配置（如果有的话）
            plan1_config = str(self.get_config("plan1.stream_config", "")).strip()
            if plan1_config:
                stream_id = auto_initiate_action._parse_stream_config_to_stream_id(plan1_config)
                if stream_id:
                    logger.debug(f"[A_Mind] 使用Plan-1配置作为手动自发起聊天流: {stream_id}")
                    return stream_id

            logger.warning("[A_Mind] 无法为手动自发起确定目标聊天流")
            return None

        except Exception as e:
            logger.error(f"[A_Mind] 获取手动自发起目标聊天流失败: {e}")
            return None

    def _validate_stream_config(self, stream_config: str) -> bool:
        """验证聊天流配置格式"""
        try:
            # 基本格式验证：platform:id:type
            if not stream_config or ":" not in stream_config:
                logger.error(f"[A_Mind] 无效的聊天流配置格式: {stream_config}")
                logger.error("[A_Mind] 正确格式示例: qq:123456:group 或 qq:123456:private")
                return False

            parts = stream_config.split(":")
            if len(parts) != 3:
                logger.error(f"[A_Mind] 聊天流配置必须包含3个部分: {stream_config}")
                logger.error("[A_Mind] 正确格式: platform:id:type")
                return False

            platform, user_id, stream_type = parts

            # 验证platform
            valid_platforms = ["qq", "telegram", "discord", "wechat"]
            if platform not in valid_platforms:
                logger.warning(f"[A_Mind] 不支持的平台: {platform}，支持的平台: {', '.join(valid_platforms)}")

            # 验证stream_type
            if stream_type not in ["group", "private", "channel"]:
                logger.error(f"[A_Mind] 无效的聊天流类型: {stream_type}")
                logger.error("[A_Mind] 支持的类型: group, private, channel")
                return False

            # 验证user_id
            if not user_id or not user_id.isdigit():
                logger.warning(f"[A_Mind] 用户ID看起来不正确: {user_id}，应该为数字")

            return True

        except Exception as e:
            logger.error(f"[A_Mind] 验证聊天流配置失败: {e}")
            return False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        """获取命令信息"""
        return CommandInfo(
            name="amind_initiate",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_initiate(\s+(\d+))?$",
            description="手动触发话题自发起 - 用法: /amind_initiate [话题ID] [stream:聊天流配置]",
        )
