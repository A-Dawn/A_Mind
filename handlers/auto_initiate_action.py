# -*- coding: utf-8 -*-
"""
自动发起Action - 完整的自发起工作流

"""

from __future__ import annotations

import time
import random
from typing import Any, Dict, List, Optional, Tuple

from src.plugin_system import ActionActivationType, BaseAction

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

# 使用相对导入，避免硬编码插件路径
from ..models.auto_send import AutoSendRequest
from ..models.topic import Topic, TopicReply  # noqa: F401  (TopicReply 可能在运行时使用)
from ..services.auto_sender import AutoSender
from ..services.brainstorm_generator import BrainstormGenerator
from ..services.decision_selector import DecisionSelector
from ..services.information_retriever import InformationRetriever
from ..services.response_monitor import ResponseMonitor
from ..utils import get_global_db_manager

logger = get_logger(__name__)


class AutoInitiateAction(BaseAction):
    """自动发起Action - 完整的自发起工作流"""

    action_name = "A_mind_auto_initiate"
    action_description = "智能话题自发起系统"
    activation_type = ActionActivationType.ALWAYS
    action_parameters: Dict[str, Any] = {}
    action_require = [
        "定时检查需要自发起的话题",
        "满足自发起条件时自动执行",
    ]
    associated_types = ["system"]

    # 类变量：关键词轮询索引（支持多plan）
    _keyword_indices: Dict[str, int] = {}

    def __init__(self, *args, plan_name: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan_name = plan_name  # 关联的plan名称，用于获取特定配置
        # 服务将在首次使用时通过属性延迟初始化
        self._info_retriever: Optional[InformationRetriever] = None
        self._brainstorm_generator: Optional[BrainstormGenerator] = None
        self._decision_selector: Optional[DecisionSelector] = None
        self._auto_sender: Optional[AutoSender] = None
        self._response_monitor: Optional[ResponseMonitor] = None

    # -------------------------
    # Lazy services
    # -------------------------
    @property
    def info_retriever(self) -> InformationRetriever:
        """信息检索器 - 延迟初始化"""
        if self._info_retriever is None:
            try:
                # 优先使用外部提供的 config_manager
                if hasattr(self, "config_manager") and getattr(self, "config_manager", None):
                    self._info_retriever = InformationRetriever(self.config_manager)
                # 尝试从插件容器获取
                elif hasattr(self, "container") and getattr(self, "container", None):
                    self._info_retriever = self.container.information_retriever
                else:
                    # 从全局插件实例获取
                    from ..plugin import _plugin_instance  # pylint: disable=import-error

                    if _plugin_instance and hasattr(_plugin_instance, "container"):
                        self._info_retriever = _plugin_instance.container.information_retriever
                    else:
                        # 备用：直接实例化（不推荐）
                        class BasicConfigManager:
                            def get(self, key, default=None):
                                defaults = {
                                    "internet_search.engine": "duckduckgo",
                                    "internet_search.timeout": 15,
                                    "internet_search.max_results": 5,
                                }
                                return defaults.get(key, default)

                            def get_model_config(self, plan_name=None, service_name=None):
                                """获取模型配置"""
                                return {
                                    "model_name": "tool_use",
                                    "fallback_model_name": "tool_use",
                                    "temperature": 0.7,
                                    "max_tokens": 1500,
                                }

                        self._info_retriever = InformationRetriever(BasicConfigManager())
            except Exception:
                # 最后的备用方案
                class BasicConfigManager:
                    def get(self, key, default=None):
                        defaults = {
                            "internet_search.engine": "duckduckgo",
                            "internet_search.timeout": 15,
                            "internet_search.max_results": 5,
                        }
                        return defaults.get(key, default)

                    def get_model_config(self, plan_name=None, service_name=None):
                        """获取模型配置"""
                        return {
                            "model_name": "tool_use",
                            "fallback_model_name": "tool_use",
                            "temperature": 0.7,
                            "max_tokens": 1500,
                        }

                self._info_retriever = InformationRetriever(BasicConfigManager())
        return self._info_retriever

    @property
    def brainstorm_generator(self) -> BrainstormGenerator:
        """头脑风暴生成器 - 延迟初始化"""
        if self._brainstorm_generator is None:
            try:
                if hasattr(self, "config_manager") and getattr(self, "config_manager", None):
                    self._brainstorm_generator = BrainstormGenerator(self.config_manager, self.plan_name)
                elif hasattr(self, "container") and getattr(self, "container", None):
                    self._brainstorm_generator = self.container.get_brainstorm_generator(self.plan_name)
                else:
                    from ..plugin import _plugin_instance  # pylint: disable=import-error

                    if _plugin_instance and hasattr(_plugin_instance, "container"):
                        self._brainstorm_generator = _plugin_instance.container.get_brainstorm_generator(self.plan_name)
                    else:
                        class BasicConfigManager:
                            def get(self, key, default=None):
                                defaults = {
                                    "llm.model_name": "tool_use",
                                    "llm.temperature": 0.7,
                                    "llm.max_tokens": 1500,
                                }
                                return defaults.get(key, default)

                            def get_model_config(self, plan_name=None, service_name=None):
                                """获取模型配置"""
                                return {
                                    "model_name": self.get("llm.model_name", "tool_use"),
                                    "fallback_model_name": "tool_use",
                                    "temperature": self.get("llm.temperature", 0.7),
                                    "max_tokens": self.get("llm.max_tokens", 1500),
                                }

                        self._brainstorm_generator = BrainstormGenerator(BasicConfigManager(), self.plan_name)
            except Exception:
                class BasicConfigManager:
                    def get(self, key, default=None):
                        defaults = {
                            "llm.model_name": "tool_use",
                            "llm.temperature": 0.7,
                            "llm.max_tokens": 1500,
                        }
                        return defaults.get(key, default)

                    def get_model_config(self, plan_name=None, service_name=None):
                        """获取模型配置"""
                        return {
                            "model_name": self.get("llm.model_name", "tool_use"),
                            "fallback_model_name": "tool_use",
                            "temperature": self.get("llm.temperature", 0.7),
                            "max_tokens": self.get("llm.max_tokens", 1500),
                        }

                self._brainstorm_generator = BrainstormGenerator(BasicConfigManager(), self.plan_name)
        return self._brainstorm_generator

    @property
    def decision_selector(self) -> DecisionSelector:
        """决策选择器 - 延迟初始化"""
        if self._decision_selector is None:
            try:
                if hasattr(self, "config_manager") and getattr(self, "config_manager", None):
                    self._decision_selector = DecisionSelector(self.config_manager, self.plan_name)
                elif hasattr(self, "container") and getattr(self, "container", None):
                    self._decision_selector = self.container.get_decision_selector(self.plan_name)
                else:
                    from ..plugin import _plugin_instance  # pylint: disable=import-error

                    if _plugin_instance and hasattr(_plugin_instance, "container"):
                        self._decision_selector = _plugin_instance.container.get_decision_selector(self.plan_name)
                    else:
                        class BasicConfigManager:
                            def get(self, key, default=None):
                                defaults = {
                                    "llm.model_name": "tool_use",
                                    "llm.temperature": 0.7,
                                    "llm.max_tokens": 1500,
                                }
                                return defaults.get(key, default)

                            def get_model_config(self, plan_name=None, service_name=None):
                                """获取模型配置"""
                                return {
                                    "model_name": self.get("llm.model_name", "tool_use"),
                                    "fallback_model_name": "tool_use",
                                    "temperature": self.get("llm.temperature", 0.7),
                                    "max_tokens": self.get("llm.max_tokens", 1500),
                                }

                        self._decision_selector = DecisionSelector(BasicConfigManager(), self.plan_name)
            except Exception:
                class BasicConfigManager:
                    def get(self, key, default=None):
                        defaults = {
                            "llm.model_name": "tool_use",
                            "llm.temperature": 0.7,
                            "llm.max_tokens": 1500,
                        }
                        return defaults.get(key, default)

                    def get_model_config(self, plan_name=None, service_name=None):
                        """获取模型配置"""
                        return {
                            "model_name": self.get("llm.model_name", "tool_use"),
                            "fallback_model_name": "tool_use",
                            "temperature": self.get("llm.temperature", 0.7),
                            "max_tokens": self.get("llm.max_tokens", 1500),
                        }

                self._decision_selector = DecisionSelector(BasicConfigManager(), self.plan_name)
        return self._decision_selector

    @property
    def auto_sender(self) -> AutoSender:
        """自动发送器 - 延迟初始化"""
        if self._auto_sender is None:
            try:
                if hasattr(self, "container") and getattr(self, "container", None):
                    self._auto_sender = self.container.auto_sender
                else:
                    from ..plugin import _plugin_instance  # pylint: disable=import-error

                    if _plugin_instance and hasattr(_plugin_instance, "container"):
                        self._auto_sender = _plugin_instance.container.auto_sender
                    else:
                        self._auto_sender = AutoSender()
            except Exception:
                self._auto_sender = AutoSender()
        return self._auto_sender

    @property
    def response_monitor(self) -> ResponseMonitor:
        """响应监控器 - 延迟初始化"""
        if self._response_monitor is None:
            try:
                if hasattr(self, "container") and getattr(self, "container", None):
                    self._response_monitor = self.container.response_monitor
                else:
                    from ..plugin import _plugin_instance  # pylint: disable=import-error

                    if _plugin_instance and hasattr(_plugin_instance, "container"):
                        self._response_monitor = _plugin_instance.container.response_monitor
                    else:
                        self._response_monitor = ResponseMonitor()
            except Exception:
                self._response_monitor = ResponseMonitor()
        return self._response_monitor

    # -------------------------
    # Stream helpers
    # -------------------------
    def _get_target_stream_id(self) -> Optional[str]:
        """获取目标聊天流ID（自动发起专用版本）"""
        try:
            # 检查途径1：当前消息聊天流
            if hasattr(self, "message") and self.message:
                if hasattr(self.message, "chat_stream") and self.message.chat_stream:
                    current_stream_id = getattr(self.message.chat_stream, "stream_id", None)
                    if current_stream_id:
                        logger.debug(f"使用当前消息聊天流: {current_stream_id}")
                        return current_stream_id
                    else:
                        logger.warning("消息聊天流存在但stream_id为空")
                else:
                    logger.warning("消息对象缺少chat_stream属性")
            else:
                logger.warning("AutoInitiateAction缺少message属性")

            # 检查途径2：Plan-1配置
            stream_config = str(self.get_config("plan1.stream_config", "")).strip()
            if stream_config:
                stream_id = self._parse_stream_config_to_stream_id(stream_config)
                if stream_id:
                    logger.debug(f"使用Plan-1配置聊天流: {stream_id}")
                    return stream_id
                else:
                    logger.warning(f"Plan-1配置无效: {stream_config}")

            # 检查途径3：默认配置
            default_stream_config = str(self.get_config("auto_initiate.default_stream_config", "")).strip()
            if default_stream_config:
                stream_id = self._parse_stream_config_to_stream_id(default_stream_config)
                if stream_id:
                    logger.debug(f"使用默认聊天流: {stream_id}")
                    return stream_id
                else:
                    logger.warning(f"默认配置无效: {default_stream_config}")

            # 所有途径都失败 - 提供详细的错误信息和解决建议
            logger.error("无法确定目标聊天流 - 请检查以下配置:")
            logger.error("  1. auto_initiate.default_stream_config - 设置默认的手动自发起聊天流")
            logger.error("  2. plan1.stream_config - 设置自动触发的聊天流")
            logger.error("  3. 确保命令在有效的聊天上下文中执行")
            logger.error("  示例配置: default_stream_config = \"qq:webui_virtual_group_qq_2584059816:group\"")
            return None

        except Exception as e:
            logger.error(f"获取目标聊天流时发生异常: {e}")
            logger.error("请检查配置文件格式是否正确")
            return None

    def _parse_stream_config_to_stream_id(self, stream_config_str: str) -> Optional[str]:
        """将 stream_config 字符串解析为 stream_id"""
        try:
            # 例：qq:123456:group
            if stream_config_str and ":" in stream_config_str:
                return stream_config_str
            return None
        except Exception:
            return None

    # -------------------------
    # Main execution
    # -------------------------
    async def execute(self) -> Tuple[bool, str]:
        """执行自动发起"""
        try:
            logger.info("[A_mind] 开始执行自动发起工作流")

            # 1) 查找需要自发起的话题
            logger.info("[A_mind] 步骤1: 查找需要自发起的话题")
            topics_to_initiate = self._find_topics_for_initiation()
            logger.info(f"[A_mind] 找到 {len(topics_to_initiate)} 个候选话题")

            # 如果找到候选：本次只处理一个候选（根据策略选择）
            if topics_to_initiate:
                priority = self.get_config("auto_initiate.activation_priority", "engagement")
                logger.info(f"[A_mind] 选择策略: {priority}")

                if priority == "recency":
                    topic = max(topics_to_initiate, key=lambda t: t.last_activity or 0)
                elif priority == "random":
                    import random

                    topic = random.choice(topics_to_initiate)
                else:
                    topic = max(topics_to_initiate, key=lambda t: t.engagement_score or 0.0)

                logger.info(
                    f"[A_mind] 选择的话题: ID={topic.id}, 标题='{topic.title}', 参与度={float(topic.engagement_score or 0.0):.2f}"
                )

                try:
                    logger.info("[A_mind] 步骤2: 执行自发起工作流")
                    success = await self._execute_initiation_workflow(topic)
                    if success:
                        return True, f"自发起完成: 成功 1/1 个话题 (ID={topic.id})"
                    return False, f"自发起失败: 话题 {topic.id}"
                except Exception as e:
                    logger.error(f"话题 {topic.id} 自发起异常: {e}")
                    return False, f"自发起失败: {str(e)}"

            # 没有候选：尝试创建一个新话题（creation_only 模式下）
            success, message = await self._execute_creation_initiation()
            if success:
                return True, f"创建型自发起成功: {message}"
            return False, f"创建型自发起失败: {message}"

        except Exception as e:
            logger.error(f"自动发起执行失败: {e}")
            return False, f"自动发起执行失败: {str(e)}"

    def _find_topics_for_initiation(self) -> List[Topic]:
        """查找需要自发起的话题"""
        try:
            active_topics = get_global_db_manager().list_topics("active")

            min_engagement = self.get_config("auto_initiate.min_engagement_for_activation", 0.3)
            max_topics = self.get_config("auto_initiate.max_topics_to_consider", 10)

            candidates: List[Topic] = []
            for topic in active_topics:
                if (topic.engagement_score or 0.0) < float(min_engagement):
                    continue

                # 避免频繁自发起
                last_initiate = topic.last_auto_initiate_at or 0
                hours_since_initiate = (time.time() - last_initiate) / 3600
                min_interval = 24  # 默认 24 小时

                if hours_since_initiate < float(min_interval):
                    continue

                # 最大自发起次数
                max_attempts = self.get_config("auto_initiate.max_auto_initiate_attempts", 3)
                if (topic.auto_initiate_count or 0) >= int(max_attempts):
                    continue

                candidates.append(topic)

            candidates.sort(key=lambda t: t.engagement_score or 0.0, reverse=True)
            return candidates[: int(max_topics)]

        except Exception as e:
            logger.error(f"查找自发起话题失败: {e}")
            return []

    async def _execute_initiation_workflow(self, topic: Topic) -> bool:
        """执行单个话题的自发起工作流"""
        try:
            logger.info(f"[A_mind] 开始执行话题 '{topic.title}' 的自发起")

            # 1) 信息检索
            context_info = await self.info_retriever.get_relevant_information(topic)

            # 2) 头脑风暴生成
            context_data = {
                "topic_title": topic.title,
                "topic_description": topic.description,
                "internet_results": context_info.get("internet_results", []),
                "knowledge_results": context_info.get("knowledge_results", []),
                "reply_count": topic.reply_count,
                "engagement_score": topic.engagement_score,
                "last_activity_hours": (time.time() - topic.last_activity) / 3600 if topic.last_activity else 24,
            }

            brainstorm_topics = await self.brainstorm_generator.generate_topics(context_data, num_topics=3)
            if not brainstorm_topics:
                logger.warning(f"[A_mind] 话题 '{topic.title}' 头脑风暴生成失败")
                return False

            # 3) 决策选择
            decision_result = await self.decision_selector.select_best_topic(brainstorm_topics, context_data)
            if not getattr(decision_result, "selected_topic", None):
                logger.warning(f"[A_mind] 话题 '{topic.title}' 决策选择失败")
                return False

            logger.info(
                f"[A_mind] 选择的话题: {decision_result.selected_topic.title} (置信度 {float(decision_result.confidence_score or 0.0):.2f})"
            )

            # 4) 生成最终发送内容
            send_content = await self._generate_send_content(
                topic=topic,
                decision_result=decision_result,
                context_info=context_info,
                context_data=context_data,
            )

            # 5) 自动发送（发送到当前聊天流）
            stream_id = self._get_target_stream_id()
            if not stream_id:
                logger.error(f"[A_mind] 无法确定目标聊天流，无法发送: topic={topic.id}")
                return False

            send_request = AutoSendRequest(
                topic_id=topic.id,
                content=send_content,
                send_type="initiate",
                priority=3,
                scheduled_time=time.time(),
                stream_id=stream_id,
                conditions={"min_engagement": 0.3, "min_interval_hours": 12, "max_sends_per_day": 2},
            )

            send_success = await self.auto_sender.schedule_send(send_request)
            if not send_success:
                logger.error(f"[A_mind] 话题 '{topic.title}' 发送调度失败")
                return False

            # 6) 启动响应监测
            try:
                monitoring_success = await self.response_monitor.start_monitoring(
                    topic.id, monitoring_window_hours=24
                )
                if monitoring_success:
                    logger.info(f"[A_mind] 话题 '{topic.title}' 响应监测已启动")
            except Exception as e:
                logger.warning(f"[A_mind] 响应监测启动失败: {e}")

            # 7) 更新话题统计
            updates = {
                "auto_initiate_count": (topic.auto_initiate_count or 0) + 1,
                "last_auto_initiate_at": time.time(),
                "status": "active",  # 重新激活
            }
            get_global_db_manager().update_topic(topic.id, updates)

            logger.info(f"[A_mind] 话题 '{topic.title}' 自发起工作流完成")
            return True

        except Exception as e:
            logger.error(f"执行单个话题自发起失败: {e}")
            return False

    async def _generate_send_content(
        self, topic: Topic, decision_result, context_info: dict, context_data: dict
    ) -> str:
        """生成发送内容 - 基于系统人设进行内容生成"""
        try:
            from src.plugin_system.apis import llm_api
            from src.plugin_system.apis.llm_api import get_available_models

            use_builtin = self.get_config("llm.use_builtin", True)
            if not use_builtin:
                logger.debug("跳过LLM内容生成，使用默认内容")
                return f"{decision_result.selected_topic.title}\n\n{decision_result.selected_topic.description}"

            system_personality = self._get_system_personality()
            enable_personality = self.get_config("auto_initiate.enable_personality_injection", True)

            logger.debug(f"[A_mind] 人设注入启用 = {enable_personality}")
            logger.debug(
                f"[A_mind] 系统人设获取 = {('None' if not system_personality else (system_personality[:50] + '...'))}"
            )

            last_activity_str = (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(topic.last_activity))
                if topic.last_activity
                else "未知"
            )

            if enable_personality and system_personality:
                content_prompt = f"""你现在是以下人设：
{system_personality}

基于这个身份和以下信息，为话题“{topic.title}”生成一段吸引人的讨论内容：

原始话题信息：
- 标题：{topic.title}
- 描述：{topic.description}
- 当前参与度：{float(topic.engagement_score or 0.0):.2f}
- 回复数量：{int(topic.reply_count or 0)}
- 最后活动：{last_activity_str}

新生成的话题方向：
- 标题：{decision_result.selected_topic.title}
- 描述：{decision_result.selected_topic.description}
- 置信度：{float(decision_result.confidence_score or 0.0):.2f}

要求：
1. 保持人设的性格特点和表达风格
2. 生成一段自然、吸引人的讨论内容，输出简体中文
3. 融入相关信息，但不要简单复述
4. 鼓励用户参与讨论
5. 内容长度适中（80-150字）
6. 直接输出生成的内容，不要添加额外说明
"""
            else:
                content_prompt = f"""基于以下信息，为话题“{topic.title}”生成一段吸引人的讨论内容：

原始话题信息：
- 标题：{topic.title}
- 描述：{topic.description}
- 当前参与度：{float(topic.engagement_score or 0.0):.2f}
- 回复数量：{int(topic.reply_count or 0)}
- 最后活动：{last_activity_str}

新生成的话题方向：
- 标题：{decision_result.selected_topic.title}
- 描述：{decision_result.selected_topic.description}
- 置信度：{float(decision_result.confidence_score or 0.0):.2f}

要求：
1. 生成一段自然、吸引人的讨论内容，输出简体中文
2. 融入相关信息，但不要简单复述
3. 鼓励用户参与讨论
4. 内容长度适中（80-150字）
5. 保持友好和开放的态度
6. 直接输出生成的内容，不要添加额外说明
"""

            logger.info(
                "[A_mind] 生成发送内容提示词 (人设注入: %s):\n%s",
                bool(enable_personality and system_personality),
                content_prompt,
            )

            try:
                available_models = get_available_models()
                model_name = self.get_config("llm.model_name", "tool_use")
                model_config = available_models.get(model_name)

                if not model_config:
                    logger.warning(f"未找到模型配置: {model_name}，使用默认配置")
                    model_config = list(available_models.values())[0] if available_models else None

                if not model_config:
                    logger.error("无可用模型配置")
                    return f"{decision_result.selected_topic.title}\n\n{decision_result.selected_topic.description}"

                ok, response, _, _ = await llm_api.generate_with_model(
                    prompt=content_prompt,
                    model_config=model_config,
                    request_type="A_mind.content_generation",
                    temperature=self.get_config("llm.temperature", 0.7),
                    max_tokens=self.get_config("llm.max_tokens", 300),
                )

                if ok and str(response).strip():
                    generated_content = str(response).strip()
                    logger.info(f"[A_mind] 成功生成发送内容，长度: {len(generated_content)}")
                    return generated_content

                logger.warning(f"[A_mind] LLM内容生成失败: {response}")
                return f"{decision_result.selected_topic.title}\n\n{decision_result.selected_topic.description}"

            except Exception as e:
                logger.error(f"LLM内容生成异常: {e}")
                return f"{decision_result.selected_topic.title}\n\n{decision_result.selected_topic.description}"

        except Exception as e:
            logger.error(f"发送内容生成异常: {e}")
            return f"{decision_result.selected_topic.title}\n\n{decision_result.selected_topic.description}"

    def _get_system_personality(self) -> str:
        """获取系统人设信息"""
        try:
            from src.config.config import global_config

            personality_config = getattr(global_config, "personality", None)
            personality_parts: List[str] = []

            if personality_config:
                if getattr(personality_config, "personality", None):
                    personality_parts.append(f"人设：{personality_config.personality}")
                if getattr(personality_config, "reply_style", None):
                    personality_parts.append(f"表达风格：{personality_config.reply_style}")
                if getattr(personality_config, "plan_style", None):
                    personality_parts.append(f"行为规则：{personality_config.plan_style}")

            if not personality_parts:
                return "你是一个喜欢上网聊天的大学生，现在正在上网和群友聊天，有时有点攻击性，有时比较温柔"

            return "；".join(personality_parts)

        except Exception as e:
            logger.warning(f"获取系统人设失败: {e}")
            return "你是一个喜欢上网聊天的大学生，现在正在上网和群友聊天，有时有点攻击性，有时比较温柔"

    async def _execute_creation_initiation(self) -> Tuple[bool, str]:
        """执行创建型自发起 - 基于信息检索创建新话题"""
        try:
            logger.info("[A_mind] 执行创建型自发起")

            search_queries = await self._get_adaptive_search_queries()
            if not search_queries:
                return False, "无可用搜索关键词"

            # 使用轮询或随机方式选择关键词，确保所有关键词都能被使用
            selected_queries = self._select_keywords_with_rotation(search_queries)
            logger.debug(f"[A_mind] 本次选择的关键词: {selected_queries}")

            search_results = []
            for query in selected_queries:
                try:
                    results = await self.info_retriever.search_internet(query, max_results=3)
                    search_results.extend(results)
                except Exception as e:
                    logger.warning(f"搜索查询 '{query}' 失败: {e}")

            if not search_results:
                return False, "信息检索失败"

            # ------------------------------------------------------------------
            # Strategy 3: Unified Creation Pipeline
            # 使用完整的 头脑风暴 -> 决策选择 -> 话题创建 流程
            # ------------------------------------------------------------------
            
            # 1. 构造上下文
            context_data = {
                "topic_title": "新建话题",  # 占位符
                "topic_description": "基于搜索结果创建新话题",
                "internet_results": search_results,
                "knowledge_results": [],
                "reply_count": 0,
                "engagement_score": 0,
                "last_activity_hours": 0,
            }

            # 2. 头脑风暴
            brainstorm_topics = await self.brainstorm_generator.generate_topics(context_data, num_topics=3)
            if not brainstorm_topics:
                 return False, "头脑风暴生成话题失败"

            # 3. 决策选择
            decision_result = await self.decision_selector.select_best_topic(brainstorm_topics, context_data)
            if not getattr(decision_result, "selected_topic", None):
                 return False, "决策选择话题失败"

            selected_topic_data = decision_result.selected_topic
            logger.info(f"[A_mind] 选中话题建议: {selected_topic_data.title} (置信度: {decision_result.confidence_score})")

            # 4. 创建话题对象
            topic = Topic(
                title=selected_topic_data.title,
                description=selected_topic_data.description,
                creator_id="auto_system",
                creator_name="自动系统",
                status="active",
                priority=1,
                visibility="public",
                # category=selected_topic_data.category # Topic模型不支持category
            )
            # 如果Topic模型没有category字段，可能会被忽略，但这没关系

            topic_id = get_global_db_manager().create_topic(topic)
            if not topic_id:
                return False, "话题创建失败"

            logger.info(f"[A_mind] 话题创建成功: '{topic.title}' (ID: {topic_id})")

            stream_id = self._get_target_stream_id()
            if not stream_id:
                logger.error("[A_mind] 无法确定目标聊天流，无法发送新话题")
                return False, "无法确定目标聊天流"

            # 自动绑定话题到聊天流
            try:
                current_topic = get_global_db_manager().get_topic(topic_id)
                if not current_topic:
                    logger.error(f"绑定失败：话题 {topic_id} 不存在")
                    return False, "话题不存在"

                if stream_id not in (current_topic.stream_ids or []):
                    new_stream_ids = (current_topic.stream_ids or []) + [stream_id]
                    update_success = get_global_db_manager().update_topic(topic_id, {"stream_ids": new_stream_ids})
                    if update_success:
                        logger.debug(f"[A_mind] 自动绑定话题 {topic_id} 到聊天流 {stream_id} 成功")
                    else:
                        logger.warning(f"[A_mind] 自动绑定话题 {topic_id} 到聊天流 {stream_id} 失败：更新数据库失败")
            except Exception as e:
                logger.warning(f"[A_mind] 自动绑定话题 {topic_id} 到聊天流 {stream_id} 失败: {e}")

            # 生成发送内容（含人设注入）
            topic.id = topic_id
            try:
                class MockDecisionResult:
                    def __init__(self, t: Topic):
                        self.selected_topic = t
                        self.confidence_score = 0.85

                decision_result = MockDecisionResult(topic)
                generated_content = await self._generate_send_content(
                    topic, decision_result, {"internet_results": search_results}, {}
                )
            except Exception as e:
                logger.warning(f"[A_mind] 新话题发送内容生成异常，使用默认回退: {e}")
                generated_content = f"💡 **{topic.title}**\n\n{topic.description}\n\n*这是基于最新信息自动创建的话题，希望能带来有趣的讨论！*"

            if not generated_content:
                generated_content = f"💡 **{topic.title}**\n\n{topic.description}\n\n*这是基于最新信息自动创建的话题，希望能带来有趣的讨论！*"

            send_request = AutoSendRequest(
                topic_id=topic_id,
                content=generated_content,
                send_type="initiate",
                priority=4,
                scheduled_time=time.time(),
                stream_id=stream_id,
                conditions={"min_engagement": 0.0, "min_interval_hours": 0, "max_sends_per_day": 3},
            )

            send_success = await self.auto_sender.schedule_send(send_request)
            if not send_success:
                return False, "发送调度失败"

            # 启动响应监测
            try:
                monitoring_success = await self.response_monitor.start_monitoring(topic_id, monitoring_window_hours=48)
                if monitoring_success:
                    logger.info(f"[A_mind] 新话题响应监测已启动: {topic_id}")
            except Exception as e:
                logger.warning(f"[A_mind] 响应监测启动失败: {e}")

            logger.info(f"[A_mind] 创建型自发起成功: {topic.title}")
            return True, f"创建话题 '{topic.title}'"

        except Exception as e:
            logger.error(f"创建型自发起失败: {e}")
            return False, f"创建失败: {str(e)}"

    # -------------------------
    # Preference-based keywords
    # -------------------------
    def _select_keywords_with_rotation(self, all_keywords: List[str]) -> List[str]:
        """选择关键词（轮询机制，确保所有关键词都能被使用）

        Args:
            all_keywords: 所有可选关键词列表

        Returns:
            本次选中的3个关键词
        """
        try:
            if not all_keywords:
                return []

            # 确定当前plan的索引键
            plan_key = self.plan_name or "default"

            # 获取或初始化轮询索引
            if plan_key not in self._keyword_indices:
                self._keyword_indices[plan_key] = 0

            # 获取当前索引
            current_index = self._keyword_indices[plan_key]
            keyword_count = len(all_keywords)
            keywords_per_batch = 3

            # 轮询选择关键词
            selected = []
            for i in range(keywords_per_batch):
                idx = (current_index + i) % keyword_count
                selected.append(all_keywords[idx])

            # 更新索引（移动3位）
            self._keyword_indices[plan_key] = (current_index + keywords_per_batch) % keyword_count

            logger.debug(f"[A_mind] 关键词轮询: plan={plan_key}, 索引={current_index}→{self._keyword_indices[plan_key]}, 选中={len(selected)}个")

            return selected

        except Exception as e:
            logger.warning(f"关键词轮询选择失败，使用随机选择: {e}")
            # 降级方案：随机选择
            return random.sample(all_keywords, min(3, len(all_keywords))) if all_keywords else []

    async def _get_adaptive_search_queries(self, stream_id: str = None) -> List[str]:
        """获取自适应搜索关键词（支持聊天流个性化）"""
        try:
            base_keywords = self.get_config(
                "auto_initiate.search_keywords",
                [
                    "最新科技新闻",
                    "人工智能发展趋势",
                    "有趣的科学发现",
                    "社会热点话题",
                    "创新技术应用",
                ],
            )

            if not stream_id:
                return list(base_keywords)

            stream_preferences = self._analyze_stream_topic_preferences(stream_id)
            adapted_keywords = self._adapt_keywords_by_preferences(list(base_keywords), stream_preferences)

            # Strategy 2: Dynamic Queries via LLM
            if self.get_config("auto_initiate.enable_dynamic_queries", False):
                dynamic_queries = await self._expand_queries_with_llm(adapted_keywords)
                logger.debug(f"为聊天流 {stream_id} 生成动态查询: {len(dynamic_queries)}")
                return dynamic_queries

            logger.debug(f"为聊天流 {stream_id} 生成自适应关键词: {len(adapted_keywords)}")
            return adapted_keywords

        except Exception as e:
            logger.warning(f"获取自适应搜索关键词失败，使用默认关键词: {e}")
            return self.get_config(
                "auto_initiate.search_keywords",
                [
                    "最新游戏推荐",
                    "最新动漫推荐",
                    "最新电子产品",
                    "最新社会热点话题",
                    "最新创新技术应用",
                ],
            )

    def _get_stream_topic_history(self, stream_id: str, days: int = 30) -> Dict[str, Any]:
        """获取聊天流的主题历史数据"""
        try:
            end_time = time.time()
            start_time = end_time - (days * 24 * 60 * 60)

            topics = get_global_db_manager().list_topics_for_stream(stream_id)
            recent_topics = [t for t in topics if (t.created_at or 0) >= start_time]

            history_data: Dict[str, Any] = {
                "total_topics": len(recent_topics),
                "total_replies": 0,
                "tech_replies": 0,
                "science_replies": 0,
                "social_replies": 0,
                "entertainment_replies": 0,
                "other_replies": 0,
            }

            for t in recent_topics:
                reply_count = int(t.reply_count or 0)
                history_data["total_replies"] += reply_count

                topic_text = f"{t.title} {t.description}".lower()

                if any(k in topic_text for k in ["科技", "技术", "ai", "人工智能", "编程", "软件", "硬件", "互联网", "数字", "创新", "研发"]):
                    history_data["tech_replies"] += reply_count
                elif any(k in topic_text for k in ["科学", "研究", "发现", "实验", "物理", "化学", "生物", "医学", "基因", "太空", "环境", "气候", "能源"]):
                    history_data["science_replies"] += reply_count
                elif any(k in topic_text for k in ["社会", "经济", "教育", "医疗", "政策", "城市", "乡村", "就业", "养老", "住房", "交通", "文化", "公益"]):
                    history_data["social_replies"] += reply_count
                elif any(k in topic_text for k in ["娱乐", "电影", "音乐", "游戏", "动漫", "综艺", "明星", "体育", "时尚", "美食", "旅游", "摄影"]):
                    history_data["entertainment_replies"] += reply_count
                else:
                    history_data["other_replies"] += reply_count

            return history_data

        except Exception as e:
            logger.warning(f"获取聊天流历史数据失败: {e}")
            return {
                "total_topics": 0,
                "total_replies": 1,  # 避免除零
                "tech_replies": 0,
                "science_replies": 0,
                "social_replies": 0,
                "entertainment_replies": 0,
                "other_replies": 0,
            }

    def _analyze_stream_topic_preferences(self, stream_id: str) -> Dict[str, float]:
        """分析聊天流的主题偏好"""
        try:
            stream_history = self._get_stream_topic_history(stream_id, days=30)
            total_replies = max(int(stream_history.get("total_replies", 1)), 1)

            preferences = {
                "tech": float(stream_history.get("tech_replies", 0)) / total_replies,
                "science": float(stream_history.get("science_replies", 0)) / total_replies,
                "social": float(stream_history.get("social_replies", 0)) / total_replies,
                "entertainment": float(stream_history.get("entertainment_replies", 0)) / total_replies,
            }

            total_weight = sum(preferences.values())
            if total_weight > 0:
                for k in list(preferences.keys()):
                    preferences[k] = preferences[k] / total_weight
            else:
                preferences = {"tech": 0.2, "science": 0.2, "social": 0.3, "entertainment": 0.3}

            logger.debug(f"聊天流 {stream_id} 的主题偏好: {preferences}")
            return preferences

        except Exception as e:
            logger.warning(f"分析聊天流主题偏好失败: {e}")
            return {"tech": 0.2, "science": 0.2, "social": 0.3, "entertainment": 0.3}

    def _adapt_keywords_by_preferences(self, base_keywords: List[str], preferences: Dict[str, float]) -> List[str]:
        """根据偏好调整关键词池（支持手动权重覆盖）"""
        try:
            tech_keywords = self.get_config("auto_initiate.tech_keywords", [])
            science_keywords = self.get_config("auto_initiate.science_keywords", [])
            social_keywords = self.get_config("auto_initiate.social_keywords", [])
            entertainment_keywords = self.get_config("auto_initiate.entertainment_keywords", [])

            # 检查是否启用手动权重
            enable_manual = self.get_config(f"{self.plan_name}.keyword_weights.enable_manual_weights", False)

            if enable_manual:
                # 使用手动配置的权重
                tech_weight = self.get_config(f"{self.plan_name}.keyword_weights.tech_weight", 0.25)
                science_weight = self.get_config(f"{self.plan_name}.keyword_weights.science_weight", 0.25)
                social_weight = self.get_config(f"{self.plan_name}.keyword_weights.social_weight", 0.25)
                entertainment_weight = self.get_config(f"{self.plan_name}.keyword_weights.entertainment_weight", 0.25)

                logger.info(f"[A_Mind] 使用手动权重: tech={tech_weight}, science={science_weight}, social={social_weight}, entertainment={entertainment_weight}")
            else:
                # 使用自动分析的偏好
                tech_weight = float(preferences.get("tech", 0.25))
                science_weight = float(preferences.get("science", 0.25))
                social_weight = float(preferences.get("social", 0.25))
                entertainment_weight = float(preferences.get("entertainment", 0.25))

                logger.debug(f"[A_Mind] 使用自动偏好: tech={tech_weight:.2f}, science={science_weight:.2f}, social={social_weight:.2f}, entertainment={entertainment_weight:.2f}")

            # Strategy 1: Epsilon-Greedy Exploration
            epsilon = self.get_config("auto_initiate.exploration_epsilon", 0.2)
            if random.random() < epsilon:
                logger.info(f"[A_Mind] 触发 Epsilon-Greedy 探索 (ε={epsilon}) - 忽略历史权重，使用均衡/反转策略")
                # 简单实现：使用均衡权重，强制引入多样性
                tech_weight = 0.25
                science_weight = 0.25
                social_weight = 0.25
                entertainment_weight = 0.25

            result_keywords: List[str] = []
            target_count = max(len(base_keywords), 1)

            # 根据权重选择关键词
            tech_count = max(0, int(target_count * tech_weight))
            if tech_count > 0 and tech_keywords:
                result_keywords.extend(list(tech_keywords)[:tech_count])

            science_count = max(0, int(target_count * science_weight))
            if science_count > 0 and science_keywords:
                result_keywords.extend(list(science_keywords)[:science_count])

            social_count = max(0, int(target_count * social_weight))
            if social_count > 0 and social_keywords:
                result_keywords.extend(list(social_keywords)[:social_count])

            entertainment_count = max(0, int(target_count * entertainment_weight))
            if entertainment_count > 0 and entertainment_keywords:
                result_keywords.extend(list(entertainment_keywords)[:entertainment_count])

            # 如果分类关键词不足，用基础关键词补充
            if len(result_keywords) < target_count:
                remaining = target_count - len(result_keywords)
                result_keywords.extend(list(base_keywords)[:remaining])

            # 去重并保持数量
            deduped: List[str] = []
            seen = set()
            for kw in result_keywords:
                if kw in seen:
                    continue
                deduped.append(kw)
                seen.add(kw)
                if len(deduped) >= target_count:
                    break

            logger.debug(f"[A_Mind] 关键词调整完成: 从{len(base_keywords)}个基础关键词扩展到{len(deduped)}个")
            return deduped

        except Exception as e:
            logger.warning(f"根据偏好调整关键词池失败: {e}")
            return base_keywords

    async def _expand_queries_with_llm(self, keywords: List[str]) -> List[str]:
        """Strategy 2: 使用LLM将关键词转化为具体的动态查询"""
        try:
            from src.plugin_system.apis import llm_api
            from src.plugin_system.apis.llm_api import get_available_models
            
            if not keywords:
                return []
                
            # 随机选取几个关键词作为种子，避免一次生成太多
            seed_keywords = random.sample(keywords, min(3, len(keywords)))
            
            current_time_str = time.strftime("%Y年%m月", time.localtime())
            
            prompt = f"""
你是一个专业的搜索引擎查询优化专家。
当前时间是：{current_time_str}

请根据以下关键词，生成3-5个具体的、具有时效性的搜索查询语句。
目的是为了搜索到最新的、有趣的、值得讨论的新闻或话题。

关键词种子：{', '.join(seed_keywords)}

要求：
1. 必须在查询中结合当前时间（{current_time_str}），确保即时性。
2. 将宽泛的关键词转化为具体的事件或趋势。
3. 查询语句要简短有力，适合搜索引擎。
4. 只输出查询语句，每行一个，不要有标点符号或序号。
5. 输出简体中文。

示例输：
2026年2月 人工智能 最新突破
2026年 春节 热门电影 票房
2026年 科技圈 重大事件
"""
            model_name = self.get_config("llm.model_name", "tool_use")
            available_models = get_available_models()
            model_config = available_models.get(model_name)
            
            if not model_config:
                 # Fallback
                 return keywords

            ok, response, _, _ = await llm_api.generate_with_model(
                    prompt=prompt,
                    model_config=model_config,
                    request_type="A_mind.dynamic_query",
                    temperature=0.7,
                    max_tokens=200,
            )
            
            if ok and response:
                queries = [line.strip() for line in str(response).strip().split('\n') if line.strip()]
                # 过滤掉可能的序号
                clean_queries = []
                for q in queries:
                    # 移除开头的 "1. " 或 "- " 或 "* "
                    # 使用更精确的正则，避免误伤 "2026年"
                    import re
                    # 匹配行首的 (数字+点+空格) 或 (减号/星号+空格)
                    q = re.sub(r'^(\d+\.|-|\*)\s*', '', q)
                    if q:
                        clean_queries.append(q)
                        
                if clean_queries:
                    logger.info(f"[A_Mind] 动态生成的查询: {clean_queries}")
                    return clean_queries
                    
            return keywords

        except Exception as e:
            logger.error(f"动态查询生成失败: {e}")
            return keywords
