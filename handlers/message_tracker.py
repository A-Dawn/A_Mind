"""
消息追踪事件处理器
"""
import time
from typing import List, Optional

from src.plugin_system import BaseEventHandler, EventType
from src.plugin_system.apis import llm_api

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
from src.plugin_system.apis.llm_api import get_available_models
# 使用相对导入
from ..models.topic import Topic, TopicReply
from ..utils import get_global_db_manager

logger = get_logger(__name__)


class MessageTrackerEventHandler(BaseEventHandler):
    """消息追踪事件处理器"""

    event_type = EventType.ON_MESSAGE
    handler_name = "amind_message_tracker"
    handler_description = "后台追踪用户消息，自动匹配相关话题并更新统计数据"

    async def execute(self, message):
        """执行消息追踪"""
        try:
            logger.info("[A_Mind] MessageTrackerEventHandler开始执行")

            if not message:
                logger.info("[A_Mind] 无消息对象，返回")
                return True, True, None, None, None

            # 获取消息内容
            message_content = getattr(message, "plain_text", getattr(message, "processed_plain_text", ""))
            logger.info(f"[A_Mind] 消息内容: {message_content[:100]}...")
            if not message_content:
                logger.info("[A_Mind] 无消息内容，返回")
                return True, True, None, None, None

            # 获取当前聊天流的活跃话题（完全隔离模式）
            current_stream_id = message.stream_id
            active_topics = get_global_db_manager().list_topics_for_stream(current_stream_id, "active")
            logger.info(f"[A_Mind] 聊天流 {current_stream_id} 的活跃话题数量: {len(active_topics)}")

            if not active_topics:
                logger.info("[A_Mind] 无活跃话题，返回")
                return True, True, None, None, None

            # 优先检测终止意图
            if await self._detect_termination_intent(message_content):
                logger.info("[A_Mind] 检测到终止意图，开始处理终止请求")

                # 识别要终止的目标话题
                target_topic = await self._identify_target_topic(message_content, active_topics)

                if target_topic:
                    # 终止目标话题
                    termination_success = await self._terminate_topic(
                        target_topic, current_stream_id, f"用户消息终止: {message_content[:50]}..."
                    )
                    if termination_success:
                        logger.info(f"[A_Mind] 用户终止话题成功: {target_topic.title}")
                        # 可以在这里添加用户通知
                        return True, True, None, None, None
                    else:
                        logger.warning(f"[A_Mind] 用户终止话题失败: {target_topic.title}")
                else:
                    logger.info("[A_Mind] 无法识别要终止的目标话题，继续进行正常匹配")
            else:
                logger.info("[A_Mind] 未检测到终止意图，继续进行话题匹配")

            # 使用LLM进行智能匹配（第二批次核心功能）
            best_match = None
            best_score = 0.0

            for topic in active_topics:
                # 检查可见性权限
                if not self._check_visibility_access(topic):
                    continue

                # 检查聊天流访问权限（完全隔离模式）
                if not self._check_stream_access(topic, current_stream_id):
                    continue

                # 计算LLM匹配分数
                score = await self._calculate_llm_match_score(message_content, topic)
                if score > best_score:
                    best_score = score
                    best_match = topic

            # 检查是否超过相似度阈值
            similarity_threshold = self.get_config("matching.similarity_threshold", 0.6)
            if best_match and best_score >= similarity_threshold:
                # 记录回复
                # 获取用户信息
                user_info = getattr(getattr(message, "message_info", None), "user_info", None)
                user_id = getattr(user_info, "user_id", "") if user_info else ""
                user_name = getattr(user_info, "user_nickname", "未知用户") if user_info else "未知用户"

                reply_record = TopicReply(
                    topic_id=best_match.id,
                    stream_id=str(current_stream_id),
                    message_id=getattr(self, "message_id", ""),
                    user_id=str(user_id),
                    user_name=str(user_name),
                    message_content=message_content,
                    reply_content="",  # 暂不生成回复内容
                    match_score=best_score,
                    quality_score=0.0,
                )

                get_global_db_manager().add_reply_record(reply_record)

                logger.info(f"[A_Mind] 消息匹配成功: {best_match.title} (分数: {best_score:.2f})")

                # 更新话题统计
                updates = {
                    "reply_count": best_match.reply_count + 1,
                    "last_activity": time.time(),
                    "engagement_score": self._update_engagement_score(best_match.engagement_score, best_score),
                }
                get_global_db_manager().update_topic(best_match.id, updates)
                logger.info(
                    f"[A_Mind] 话题统计已更新: ID={best_match.id}, 新回复数={updates['reply_count']}, 新参与度={updates['engagement_score']:.2f}"
                )

                logger.info(f"[A_Mind] 消息匹配到话题: {best_match.title} (分数: {best_score:.2f})")
                return True, True, None, None, None
            else:
                logger.info(
                    f"[A_Mind] 消息未匹配到任何活跃话题 (最高分数: {best_score:.2f}, 阈值: {similarity_threshold})"
                )
                return True, True, None, None, None

        except Exception as e:
            logger.error(f"消息追踪执行失败: {e}")
            return True, False, None, None, str(e)

    async def _calculate_llm_match_score(self, message: str, topic: Topic) -> float:
        """使用LLM计算消息与话题的匹配分数"""
        try:
            # 获取配置参数
            keyword_boost = self.get_config("matching.keyword_boost", 1.2)
            context_window = self.get_config("matching.context_window", 10)
            time_decay_factor = self.get_config("matching.time_decay_factor", 0.95)

            # 1. 关键词匹配基础分数
            keyword_score = self._calculate_keyword_score(message, topic)

            # 2. LLM语义相似度分析
            llm_score = await self._calculate_llm_similarity(message, topic)

            # 3. 上下文相关性分析
            context_score = self._calculate_context_relevance(message, topic, context_window)

            # 4. 时间衰减因子
            time_score = self._calculate_time_decay(topic)

            # 综合计算最终分数（优化权重分配）
            final_score = (
                llm_score * 0.6  # LLM语义相似度权重60%（提高）
                + keyword_score * keyword_boost * 0.15  # 关键词匹配权重15%（降低，因为分词更准确）
                + context_score * 0.2  # 上下文相关性权重20%（提高）
                + time_score * 0.05  # 时间衰减权重5%（保持）
            )

            # 确保分数在0-1范围内
            return max(0.0, min(1.0, final_score))

        except Exception as e:
            logger.error(f"LLM匹配分数计算失败: {e}")
            # 降级到关键词匹配
            return self._calculate_keyword_score(message, topic)

    async def _calculate_llm_similarity(self, message: str, topic: Topic) -> float:
        """使用LLM计算语义相似度"""
        try:
            # 获取LLM配置
            use_builtin = self.get_config("llm.use_builtin", True)
            if not use_builtin:
                logger.debug("跳过LLM匹配，使用关键词匹配")
                return 0.0

            # 构建提示词
            matching_prompt = self.get_config("prompts.matching_system_prompt", "")
            if not matching_prompt:
                matching_prompt = "你是一个话题匹配专家，负责分析消息内容与话题描述的相似性。请返回一个0-1之间的匹配分数，只返回数字。"

            # 构建分析文本
            analysis_text = f"""
话题标题：{topic.title}
话题描述：{topic.description}
用户消息：{message}

请分析用户消息与话题的相关性，返回0-1之间的相似度分数。
考虑因素：
1. 语义相关性
2. 关键词重叠
3. 话题意图匹配
4. 上下文一致性

只返回一个0-1之间的小数，不要其他内容。
"""

            # 调用LLM API
            try:
                # 获取模型配置
                available_models = get_available_models()
                model_name = self.get_config("llm.model_name", "tool_use")
                model_config = available_models.get(model_name)

                if not model_config:
                    logger.warning(f"未找到模型配置: {model_name}，使用默认配置")
                    model_config = list(available_models.values())[0] if available_models else None

                if not model_config:
                    logger.error("无可用模型配置")
                    return 0.0

                ok, response, _, _ = await llm_api.generate_with_model(
                    prompt=analysis_text,
                    model_config=model_config,
                    request_type="amind.similarity",
                    temperature=self.get_config("llm.temperature", 0.1),
                    max_tokens=self.get_config("llm.max_tokens", 50),
                )

                if not ok:
                    logger.error(f"LLM调用失败: {response}")
                    return 0.0

                # 解析响应
                score_text = response.strip()
                try:
                    score = float(score_text)
                    return max(0.0, min(1.0, score))
                except ValueError:
                    logger.warning(f"LLM返回的不是有效分数: {score_text}")
                    return 0.5  # 默认中等相似度

            except Exception as e:
                logger.error(f"LLM API调用失败: {e}")
                return 0.0

        except Exception as e:
            logger.error(f"LLM相似度计算异常: {e}")
            return 0.0

    def _calculate_keyword_score(self, message: str, topic: Topic) -> float:
        """计算关键词匹配分数（智能中文分词）"""
        try:
            # 转换为小写进行匹配
            message_lower = message.lower()
            title_lower = topic.title.lower()
            desc_lower = (topic.description or "").lower()

            # 使用智能分词或降级到简单分词
            try:
                import jieba
                JIEBA_AVAILABLE = True
            except ImportError:
                JIEBA_AVAILABLE = False

            if JIEBA_AVAILABLE:
                # jieba分词 + 基础停用词过滤
                stop_words = {
                    "的",
                    "了",
                    "和",
                    "是",
                    "就",
                    "都",
                    "而",
                    "及",
                    "与",
                    "着",
                    "或",
                    "一个",
                    "没有",
                    "我们",
                    "你们",
                    "他们",
                    "这个",
                    "那个",
                    "这些",
                    "那些",
                    "这里",
                    "那里",
                    "什么",
                    "怎么",
                    "为什么",
                    "怎么样",
                }

                def smart_tokenize(text):
                    """智能分词并过滤停用词"""
                    if not text.strip():
                        return set()
                    words = jieba.cut(text)
                    # 过滤单字和停用词，保留2字以上的有意义词汇
                    filtered_words = {word for word in words if len(word) > 1 and word not in stop_words}
                    return filtered_words

                title_words = smart_tokenize(title_lower)
                desc_words = smart_tokenize(desc_lower)
                message_words = smart_tokenize(message_lower)
            else:
                # 降级到简单分词（按空格和标点）
                def simple_tokenize(text):
                    import re

                    # 按中文标点和空格分词
                    words = re.split(r'[\s,，.。!！?？;；:：""' "（）()【】《》<>]+", text)
                    return {word for word in words if len(word) > 1}

                title_words = simple_tokenize(title_lower)
                desc_words = simple_tokenize(desc_lower)
                message_words = simple_tokenize(message_lower)

            # 计算词语重叠度（使用Jaccard相似度）
            if not title_words and not desc_words:
                return 0.0

            # 标题匹配度
            if title_words:
                title_intersection = len(title_words & message_words)
                title_union = len(title_words | message_words)
                title_score = title_intersection / title_union if title_union > 0 else 0.0
            else:
                title_score = 0.0

            # 描述匹配度
            if desc_words:
                desc_intersection = len(desc_words & message_words)
                desc_union = len(desc_words | message_words)
                desc_score = desc_intersection / desc_union if desc_union > 0 else 0.0
            else:
                desc_score = 0.0

            # 综合评分：标题权重更高
            final_score = title_score * 0.7 + desc_score * 0.3

            return min(final_score, 1.0)

        except Exception as e:
            logger.warning(f"关键词匹配计算异常: {e}")
            return 0.0

    def _calculate_context_relevance(self, message: str, topic: Topic, context_window: int) -> float:
        """计算上下文相关性（改进版）"""
        try:
            # 获取最近的回复记录作为上下文
            recent_replies = get_global_db_manager().get_recent_replies(topic.id, context_window)

            if not recent_replies:
                # 无上下文时，基于话题活跃度返回基础相关性
                days_since_creation = (time.time() - topic.created_at) / (24 * 3600)
                if days_since_creation < 1:
                    return 0.7  # 新话题，假设相关性较高
                elif days_since_creation < 7:
                    return 0.6  # 近期话题
                else:
                    return 0.4  # 较旧话题

            # 计算消息与最近回复的相似度（带时间权重衰减）
            context_scores = []
            total_weight = 0

            for i, reply in enumerate(recent_replies):
                # 时间权重：越近的回复权重越高
                time_weight = 1.0 / (i + 1)  # 最新回复权重1.0，依次递减

                # 计算相似度
                score = self._calculate_keyword_score(
                    message, Topic(title="", description=reply["message_content"], creator_id="")
                )

                # 质量权重：考虑回复的质量分数（如果有的话）
                quality_weight = (reply["quality_score"] if "quality_score" in reply else 0.5) + 0.5  # 0.5-1.5范围

                # 综合权重
                final_weight = time_weight * quality_weight
                weighted_score = score * final_weight

                context_scores.append(weighted_score)
                total_weight += final_weight

            # 返回加权平均上下文相关性
            if context_scores and total_weight > 0:
                weighted_avg = sum(context_scores) / total_weight
                # 确保在合理范围内
                return max(0.1, min(0.9, weighted_avg))
            else:
                return 0.5

        except Exception as e:
            logger.warning(f"上下文相关性计算失败: {e}")
            return 0.5

    def _calculate_time_decay(self, topic: Topic) -> float:
        """计算时间衰减因子（改进版）"""
        try:
            base_decay_factor = self.get_config("matching.time_decay_factor", 0.95)

            current_time = time.time()
            hours_since_activity = (current_time - topic.last_activity) / 3600 if topic.last_activity else 24

            # 基础时间衰减
            base_decay = base_decay_factor**hours_since_activity

            # 活跃度调整因子
            activity_bonus = 0.0

            # 1. 回复数量奖励：回复越多，衰减越慢
            if topic.reply_count > 20:
                activity_bonus += 0.2  # 高活跃话题奖励
            elif topic.reply_count > 10:
                activity_bonus += 0.1  # 中等活跃话题奖励
            elif topic.reply_count > 5:
                activity_bonus += 0.05  # 轻度活跃话题奖励

            # 2. 参与度奖励：参与度越高，衰减越慢
            if topic.engagement_score > 0.8:
                activity_bonus += 0.15  # 高参与度奖励
            elif topic.engagement_score > 0.6:
                activity_bonus += 0.1  # 中等参与度奖励
            elif topic.engagement_score > 0.4:
                activity_bonus += 0.05  # 低参与度奖励

            # 3. 新话题保护期（创建后24小时内）
            hours_since_creation = (current_time - topic.created_at) / 3600
            if hours_since_creation < 24:
                activity_bonus += 0.1  # 新话题给予额外保护

            # 4. 长期活跃奖励（活跃超过7天的话题）
            if hours_since_creation > 168:  # 7天
                activity_bonus += 0.05  # 长期活跃奖励

            # 应用活跃度调整（衰减因子不能超过1.0）
            adjusted_decay = min(1.0, base_decay + activity_bonus)

            # 确保衰减因子在合理范围内
            return max(0.1, min(1.0, adjusted_decay))

        except Exception as e:
            logger.warning(f"时间衰减计算失败: {e}")
            return 0.8  # 默认衰减值

    def _check_visibility_access(self, topic: Topic) -> bool:
        """检查用户是否有权限访问话题"""
        try:
            user_id = str(getattr(self, "user_id", ""))

            if topic.visibility == "public":
                return True
            elif topic.visibility == "private":
                # 检查用户是否在允许列表中
                return user_id in (topic.allowed_users or [])
            else:
                return False

        except Exception as e:
            logger.error(f"可见性检查失败: {e}")
            return False

    def _check_stream_access(self, topic: Topic, current_stream_id: str) -> bool:
        """检查当前聊天流是否有权限访问话题（完全隔离模式）"""
        try:

            # 检查话题是否绑定到当前聊天流
            if current_stream_id not in topic.stream_ids:
                return False

            # 检查聊天流状态是否为活跃
            stream_state = get_global_db_manager().get_topic_stream_state(topic.id, current_stream_id)
            if stream_state and stream_state.status != "active":
                return False

            return True

        except Exception as e:
            logger.warning(f"聊天流权限检查失败: {e}")
            return False

    async def _detect_termination_intent(self, message: str) -> bool:
        """检测消息是否包含终止意图"""
        try:
            # 终止意图关键词检测
            termination_keywords = [
                "别再提",
                "不要提",
                "停止",
                "结束",
                "终止",
                "完了",
                "算了",
                "别说了",
                "不说这个了",
                "换个话题",
                "不聊了",
                "不聊这个了",
                "这个话题结束了",
                "这个话题别说了",
            ]

            message_lower = message.lower()

            # 检查是否包含终止关键词
            for keyword in termination_keywords:
                if keyword in message_lower:
                    logger.info(f"[A_Mind] 检测到终止意图关键词: {keyword}")
                    return True

            # 如果启用了LLM检测，进一步分析
            use_llm_detection = self.get_config("state_check.enable_termination_detection", False)
            if use_llm_detection:
                return await self._llm_termination_detection(message)

            return False

        except Exception as e:
            logger.warning(f"终止意图检测失败: {e}")
            return False

    async def _llm_termination_detection(self, message: str) -> bool:
        """使用LLM进行终止意图检测"""
        try:
            # 获取LLM配置
            available_models = get_available_models()
            model_name = self.get_config("llm.model_name", "tool_use")
            model_config = available_models.get(model_name)

            if not model_config:
                logger.warning("无可用LLM模型配置用于终止意图检测")
                return False

            # 构建检测提示词
            prompt = f"""请分析以下消息是否表达了终止某个话题的意图：

消息内容："{message}"

请判断用户是否想要：
1. 终止或结束某个特定话题的讨论
2. 明确表示不再讨论某个话题
3. 要求停止某个话题的继续

如果用户表达了上述任一意图，返回true，否则返回false。
只返回true或false，不要其他内容。"""

            ok, response, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="amind.termination_detection",
                temperature=0.1,
                max_tokens=10,
            )

            if not ok:
                logger.warning(f"LLM终止意图检测失败: {response}")
                return False

            response_clean = response.strip().lower()
            return response_clean in ["true", "是", "yes", "1"]

        except Exception as e:
            logger.error(f"LLM终止意图检测异常: {e}")
            return False

    async def _identify_target_topic(self, message: str, active_topics: List[Topic]) -> Optional[Topic]:
        """识别用户要终止的目标话题"""
        try:
            # 从消息中提取话题名称
            topic_names = [topic.title for topic in active_topics]

            # 简单的话题名称匹配
            for topic in active_topics:
                if topic.title in message:
                    logger.info(f"[A_Mind] 通过直接匹配识别目标话题: {topic.title}")
                    return topic

            # 如果没有直接匹配，使用LLM进行语义匹配
            use_llm_detection = self.get_config("state_check.enable_termination_detection", False)
            if use_llm_detection:
                return await self._llm_topic_identification(message, active_topics)

            return None

        except Exception as e:
            logger.warning(f"目标话题识别失败: {e}")
            return None

    async def _llm_topic_identification(self, message: str, active_topics: List[Topic]) -> Optional[Topic]:
        """使用LLM识别要终止的目标话题"""
        try:
            available_models = get_available_models()
            model_name = self.get_config("llm.model_name", "tool_use")
            model_config = available_models.get(model_name)

            if not model_config:
                return None

            # 构建话题识别提示词
            topic_list = "\n".join(
                [f"{i + 1}. {topic.title}: {topic.description}" for i, topic in enumerate(active_topics)]
            )

            prompt = f"""用户消息："{message}"

活跃话题列表：
{topic_list}

请判断用户想要终止哪个话题。如果能够确定，返回对应的话题序号（1、2、3等），如果无法确定或用户没有表达终止特定话题的意图，返回0。"""

            ok, response, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="amind.topic_identification",
                temperature=0.1,
                max_tokens=5,
            )

            if not ok:
                return None

            try:
                topic_index = int(response.strip()) - 1
                if 0 <= topic_index < len(active_topics):
                    identified_topic = active_topics[topic_index]
                    logger.info(f"[A_Mind] LLM识别目标话题: {identified_topic.title}")
                    return identified_topic
            except ValueError:
                pass

            return None

        except Exception as e:
            logger.error(f"LLM话题识别异常: {e}")
            return None

    async def _terminate_topic(self, topic: Topic, current_stream_id: str, termination_reason: str = "用户明确终止") -> bool:
        """终止指定话题（完全隔离模式：在当前聊天流中终止）"""
        try:

            # 在完全隔离模式下，只更新当前聊天流的状态
            stream_updates = {"status": "terminated"}
            success = get_global_db_manager().update_topic_stream_state(topic.id, current_stream_id, stream_updates)

            if success:
                logger.info(f"[A_Mind] 话题在聊天流{current_stream_id}中已终止: {topic.title} (ID: {topic.id}), 原因: {termination_reason}")
                # 可以在这里添加通知逻辑
            else:
                logger.error(f"[A_Mind] 话题终止失败: {topic.title} (ID: {topic.id})")

            return success

        except Exception as e:
            logger.error(f"终止话题异常: {e}")
            return False

    def _update_engagement_score(self, current_score: float, match_score: float) -> float:
        """更新参与度分数"""
        try:
            # 加权平均更新：当前分数权重70%，新匹配分数权重30%
            new_score = current_score * 0.7 + match_score * 0.3
            # 确保分数在合理范围内
            return max(0.0, min(1.0, new_score))
        except Exception as e:
            logger.warning(f"参与度分数更新异常: {e}")
            return current_score
