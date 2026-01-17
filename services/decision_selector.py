"""
决策选择器 - 从多个话题中选择最佳选项
"""

import json
from typing import List, Dict, Any, Optional

try:
    from ..models.brainstorm import BrainstormTopic, DecisionResult
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from models.brainstorm import BrainstormTopic, DecisionResult

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

logger = get_logger(__name__)


class DecisionSelector:
    """决策选择器 - 从多个话题中选择最佳选项"""

    def __init__(self, config_manager, plan_name: str = None):
        """初始化决策选择器

        Args:
            config_manager: 配置管理器实例
            plan_name: 关联的plan名称，用于获取特定配置
        """
        self.config = config_manager
        self.plan_name = plan_name

    async def select_best_topic(self, topics: List[BrainstormTopic], context: Dict[str, Any]) -> DecisionResult:
        """从多个话题中选择最佳选项"""
        try:
            if not topics:
                return DecisionResult(
                    selected_topic=None, confidence_score=0.0, reasoning="无可用话题选项", alternatives=[]
                )

            if len(topics) == 1:
                return DecisionResult(
                    selected_topic=topics[0], confidence_score=0.8, reasoning="只有一个话题选项", alternatives=[]
                )

            # 使用LLM进行智能选择
            decision_result = await self._llm_topic_selection(topics, context)

            if decision_result and decision_result.selected_topic:
                logger.info(f"[A_Mind] LLM决策选择完成: {decision_result.selected_topic.title}")
                return decision_result

            # LLM失败时使用规则选择
            logger.warning("[A_Mind] LLM决策选择失败，使用规则选择")
            return self._rule_based_selection(topics, context)

        except Exception as e:
            logger.error(f"话题选择失败: {e}")
            # 返回第一个话题作为fallback
            return DecisionResult(
                selected_topic=topics[0] if topics else None,
                confidence_score=0.3,
                reasoning=f"选择失败，使用默认选项: {str(e)}",
                alternatives=topics[1:] if len(topics) > 1 else [],
            )

    async def _llm_topic_selection(
        self, topics: List[BrainstormTopic], context: Dict[str, Any]
    ) -> Optional[DecisionResult]:
        """使用LLM进行话题选择"""
        try:
            # 构建选择提示词
            selection_prompt = self.config.get("prompts.initiate_decision_prompt", "")
            if not selection_prompt:
                selection_prompt = """
请从以下话题选项中选择最适合发起讨论的一个：

原始话题：{original_topic}
当前参与情况：{engagement_context}

候选话题列表：
{topic_list}

选择标准：
1. 相关性：与原始话题的相关程度
2. 新颖性：话题的新鲜感和吸引力
3. 参与潜力：能够激发用户讨论的可能性
4. 时机合适性：当前是否是讨论的好时机
5. 多样性：避免与现有话题过度重复

请返回JSON格式：
{{
  "selected_index": 0,
  "confidence_score": 0.0,
  "reasoning": "选择理由",
  "criteria_scores": {{
    "relevance": 0.0,
    "novelty": 0.0,
    "engagement_potential": 0.0,
    "timing": 0.0,
    "diversity": 0.0
  }}
}}
"""

            # 准备数据
            original_topic = context.get("topic_title", "")
            engagement_context = self._format_engagement_context(context)

            topic_list = ""
            for i, topic in enumerate(topics):
                topic_list += f"""
{i + 1}. 标题：{topic.title}
   描述：{topic.description}
   分类：{topic.category}
   新颖性：{topic.novelty_score:.1f}
   参与潜力：{topic.engagement_potential:.1f}
   标签：{", ".join(topic.tags)}
   理由：{topic.reasoning}
"""

            # 填充提示词
            prompt_text = selection_prompt.format(
                original_topic=original_topic, engagement_context=engagement_context, topic_list=topic_list
            )

            # 获取决策选择专用的模型配置
            model_config = self.config.get_model_config(self.plan_name, 'decision')

            # 调用LLM（支持备选模型）
            try:
                response = await self._call_llm_with_fallback(
                    prompt_text,
                    request_type="amind.decision",
                    temperature=model_config['temperature'],
                    max_tokens=model_config['max_tokens'],
                    primary_model=model_config['model_name'],
                    fallback_model=model_config['fallback_model_name'],
                )

                if not response:
                    logger.warning("所有LLM模型调用失败，使用规则选择")
                    return self._rule_based_selection(topics, context)

                # 解析响应
                try:
                    # 首先检查响应是否有效
                    if not response or not isinstance(response, str):
                        logger.warning(f"[A_Mind] LLM返回无效响应类型: {type(response)}")
                        return None

                    # 清理响应文本，移除可能的markdown代码块标记
                    cleaned_response = response.strip()

                    # 检查清理后的响应是否为空
                    if not cleaned_response:
                        logger.warning("[A_Mind] LLM返回空响应")
                        return None

                    # 移除可能的markdown代码块标记
                    if cleaned_response.startswith("```json"):
                        cleaned_response = cleaned_response[7:]
                    if cleaned_response.startswith("```"):
                        cleaned_response = cleaned_response[3:]
                    if cleaned_response.endswith("```"):
                        cleaned_response = cleaned_response[:-3]

                    cleaned_response = cleaned_response.strip()

                    # 再次检查清理后是否为空
                    if not cleaned_response:
                        logger.warning("[A_Mind] 清理后的响应为空")
                        return None

                    # 尝试查找JSON的开始和结束
                    json_start = cleaned_response.find("{")
                    json_end = cleaned_response.rfind("}") + 1

                    json_content = ""
                    if json_start != -1 and json_end > json_start:
                        json_content = cleaned_response[json_start:json_end]
                    else:
                        # 如果没有找到完整的JSON，尝试直接解析
                        json_content = cleaned_response

                    # 验证JSON内容是否合理（至少包含基本结构）
                    if len(json_content.strip()) < 10:  # 太短不可能是有效JSON
                        logger.warning(f"[A_Mind] JSON内容太短: '{json_content}'")
                        return None

                    # 尝试解析JSON
                    result = json.loads(json_content)

                    selected_index = result.get("selected_index", 1) - 1  # 转换为0-based索引

                    if 0 <= selected_index < len(topics):
                        selected_topic = topics[selected_index]
                        confidence_score = result.get("confidence_score", 0.5)
                        reasoning = result.get("reasoning", "LLM选择")
                        criteria_scores = result.get("criteria_scores", {})

                        return DecisionResult(
                            selected_topic=selected_topic,
                            confidence_score=confidence_score,
                            reasoning=reasoning,
                            alternatives=[t for t in topics if t != selected_topic],
                            selection_criteria=criteria_scores,
                        )
                    else:
                        logger.warning(f"[A_Mind] LLM选择的索引 {selected_index} 超出范围 [0, {len(topics) - 1}]")

                except json.JSONDecodeError as e:
                    logger.warning(f"LLM选择返回的不是有效JSON (解析错误: {e}): {response[:200]}...")
                except Exception as e:
                    logger.warning(f"LLM选择JSON解析异常: {e}, 响应内容: {response[:200]}...")

            except Exception as e:
                logger.error(f"LLM话题选择调用失败: {e}")

            return None

        except Exception as e:
            logger.error(f"LLM话题选择异常: {e}")
            return None

    def _rule_based_selection(self, topics: List[BrainstormTopic], context: Dict[str, Any]) -> DecisionResult:
        """基于规则的话题选择"""
        try:
            # 计算每个话题的综合评分
            scored_topics = []

            for topic in topics:
                # 综合评分 = 新颖性 * 0.4 + 参与潜力 * 0.4 + 相关性 * 0.2
                overall_score = (
                    topic.novelty_score * 0.4 + topic.engagement_potential * 0.4 + topic.relevance_score * 0.2
                )

                scored_topics.append((topic, overall_score))

            # 按评分排序
            scored_topics.sort(key=lambda x: x[1], reverse=True)

            # 选择最高分的话题
            selected_topic, confidence_score = scored_topics[0]

            # 构建选择理由
            reasoning = f"基于规则选择: 新颖性{selected_topic.novelty_score:.2f}, 参与潜力{selected_topic.engagement_potential:.2f}, 相关性{selected_topic.relevance_score:.2f}"

            return DecisionResult(
                selected_topic=selected_topic,
                confidence_score=min(confidence_score, 0.9),  # 规则选择的置信度上限为0.9
                reasoning=reasoning,
                alternatives=[topic for topic, _ in scored_topics[1:]],
                selection_criteria={
                    "novelty": selected_topic.novelty_score,
                    "engagement_potential": selected_topic.engagement_potential,
                    "relevance": selected_topic.relevance_score,
                },
            )

        except Exception as e:
            logger.error(f"规则选择失败: {e}")
            # 返回第一个话题
            return DecisionResult(
                selected_topic=topics[0] if topics else None,
                confidence_score=0.3,
                reasoning="规则选择失败，使用默认选项",
                alternatives=topics[1:] if len(topics) > 1 else [],
            )

    def _format_engagement_context(self, context: Dict[str, Any]) -> str:
        """格式化参与情况上下文"""
        try:
            reply_count = context.get("reply_count", 0)
            engagement_score = context.get("engagement_score", 0.0)
            last_activity_hours = context.get("last_activity_hours", 24)

            if reply_count == 0:
                return "话题刚刚创建，暂无用户参与"
            elif engagement_score > 0.7:
                return f"话题参与度很高（{engagement_score:.2f}），最近{last_activity_hours:.1f}小时内有{reply_count}条回复"
            elif engagement_score > 0.4:
                return f"话题参与度中等（{engagement_score:.2f}），最近{last_activity_hours:.1f}小时内有{reply_count}条回复"
            else:
                return f"话题参与度较低（{engagement_score:.2f}），最近{last_activity_hours:.1f}小时内有{reply_count}条回复"

        except Exception as e:
            logger.warning(f"格式化参与上下文失败: {e}")
            return "参与情况未知"

    async def _call_llm_with_fallback(self, prompt: str, request_type: str, temperature: float = 0.7, max_tokens: int = 1000,
                                     primary_model: str = None, fallback_model: str = None) -> str:
        """调用LLM，支持备选模型回退"""
        from src.plugin_system.apis.llm_api import get_available_models
        from src.plugin_system.apis import llm_api

        available_models = get_available_models()

        # 使用传入的模型名称或默认配置
        if primary_model is None:
            primary_model_name = self.config.get("llm.model_name", "tool_use")
        else:
            primary_model_name = primary_model

        if fallback_model is None:
            fallback_model_name = self.config.get("llm.fallback_model_name", "tool_use")
        else:
            fallback_model_name = fallback_model

        primary_model_config = available_models.get(primary_model_name)

        # 尝试首选模型
        if primary_model_config:
            try:
                logger.info(f"[A_Mind] 尝试使用首选模型: {primary_model_name}")
                ok, response, _, _ = await llm_api.generate_with_model(
                    prompt=prompt,
                    model_config=primary_model_config,
                    request_type=request_type,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                if ok and response and isinstance(response, str) and response.strip():
                    logger.info(f"[A_Mind] 首选模型调用成功")
                    return response
                else:
                    logger.warning(f"[A_Mind] 首选模型返回无效响应: ok={ok}, response={response[:100]}...")
            except Exception as e:
                logger.error(f"[A_Mind] 首选模型调用异常: {e}")

        # 尝试配置文件中指定的备选模型
        if fallback_model_name and fallback_model_name != primary_model_name:
            fallback_model_config = available_models.get(fallback_model_name)
            if fallback_model_config:
                try:
                    logger.info(f"[A_Mind] 尝试使用配置的备选模型: {fallback_model_name}")
                    ok, response, _, _ = await llm_api.generate_with_model(
                        prompt=prompt,
                        model_config=fallback_model_config,
                        request_type=request_type,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    if ok and response and isinstance(response, str) and response.strip():
                        logger.info(f"[A_Mind] 备选模型 {fallback_model_name} 调用成功")
                        return response
                    else:
                        logger.warning(f"[A_Mind] 备选模型 {fallback_model_name} 返回无效响应")
                except Exception as e:
                    logger.error(f"[A_Mind] 备选模型 {fallback_model_name} 调用异常: {e}")
            else:
                logger.warning(f"[A_Mind] 配置的备选模型 '{fallback_model_name}' 不可用")

        logger.error("[A_Mind] 首选模型和备选模型调用都失败")
        return ""
