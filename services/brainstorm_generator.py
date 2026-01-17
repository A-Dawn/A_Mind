"""
头脑风暴生成器 - 基于LLM生成多个话题
"""

import json
import random
from typing import Dict, Any, List

try:
    from ..models.brainstorm import BrainstormTopic
    from ..models.search import SearchResult, KnowledgeItem
except ImportError:
    # 直接导入时的备用方案
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from models.brainstorm import BrainstormTopic
    from models.search import SearchResult, KnowledgeItem

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
from src.config.config import global_config

logger = get_logger(__name__)


class BrainstormGenerator:
    """头脑风暴生成器 - 基于LLM生成多个话题"""

    def __init__(self, config_manager, plan_name: str = None):
        """初始化头脑风暴生成器

        Args:
            config_manager: 配置管理器实例
            plan_name: 关联的plan名称，用于获取特定配置
        """
        self.config = config_manager
        self.plan_name = plan_name

    async def generate_topics(self, context: Dict[str, Any], num_topics: int = 5) -> List[BrainstormTopic]:
        """生成多个相关话题"""
        try:
            # 检查是否启用人设注入
            enable_personality = self.config.get("auto_initiate.enable_personality_injection", True)
            personality_info = ""

            if enable_personality:
                # 获取系统人设配置
                personality_info = self._get_system_personality()

            # 检查是否使用兜底话题
            fallback_probability = self.config.get("auto_initiate.fallback_topic_probability", 0.3)
            use_fallback = False

            if fallback_probability > 0:
                use_fallback = random.random() < fallback_probability

            if use_fallback:
                return self._generate_fallback_topics_from_config(num_topics, context)

            # 构建生成提示词
            generation_prompt = self.config.get("prompts.initiate_brainstorm_prompt", "")
            if not generation_prompt:
                generation_prompt = """
请基于以下信息进行头脑风暴，生成{num_topics}个相关的话题建议：

系统人设：{personality_info}

上下文信息：
- 原始话题：{original_topic}
- 描述：{description}
- 相关搜索结果：{search_results}
- 知识库内容：{knowledge_content}

要求：
1. 每个话题都要符合系统人设的性格特点和表达风格
2. 话题应该与原始主题相关但不重复
3. 考虑用户参与度和讨论潜力
4. 提供简洁有力的标题和描述
5. 为每个话题添加合适的标签

请严格返回JSON格式，不要输出任何其他内容：
{{
  "topics": [
    {{
      "title": "话题标题",
      "description": "话题描述（50字以内）",
      "category": "话题分类",
      "novelty_score": 0.0,
      "engagement_potential": 0.0,
      "reasoning": "生成理由",
      "tags": ["标签1", "标签2"]
    }}
  ]
}}
"""

            # 准备上下文数据
            original_topic = context.get("topic_title", "")
            description = context.get("topic_description", "")
            search_results = self._format_search_results(context.get("internet_results", []))
            knowledge_content = self._format_knowledge_results(context.get("knowledge_results", []))

            # 填充提示词
            prompt_text = generation_prompt.format(
                num_topics=num_topics,
                personality_info=personality_info,
                original_topic=original_topic,
                description=description,
                search_results=search_results,
                knowledge_content=knowledge_content,
            )

            # 获取头脑风暴专用的模型配置
            model_config = self.config.get_model_config(self.plan_name, 'brainstorm')

            # 调用LLM生成话题（支持备选模型）
            try:
                response = await self._call_llm_with_fallback(
                    prompt_text,
                    request_type="amind.brainstorm",
                    temperature=model_config['temperature'],
                    max_tokens=model_config['max_tokens'],
                    primary_model=model_config['model_name'],
                    fallback_model=model_config['fallback_model_name'],
                )

                if not response:
                    logger.warning("所有LLM模型调用失败，使用备选方案")
                    return self._generate_fallback_topics(context, num_topics)

                # 解析JSON响应
                try:
                    # 首先检查响应是否有效
                    if not response or not isinstance(response, str):
                        logger.warning(f"[A_Mind] LLM返回无效响应类型: {type(response)}")
                        return self._generate_fallback_topics(context, num_topics)

                    # 清理响应文本，移除可能的markdown代码块标记
                    cleaned_response = response.strip()

                    # 检查清理后的响应是否为空
                    if not cleaned_response:
                        logger.warning("[A_Mind] LLM返回空响应")
                        return self._generate_fallback_topics(context, num_topics)

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
                        return self._generate_fallback_topics(context, num_topics)

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
                        return self._generate_fallback_topics(context, num_topics)

                    # 尝试解析JSON
                    result = json.loads(json_content)

                    topics_data = result.get("topics", [])

                    if not topics_data:
                        logger.warning(f"[A_Mind] LLM返回的JSON中没有topics字段: {result}")
                        return self._generate_fallback_topics(context, num_topics)

                    topics = []
                    for topic_data in topics_data[:num_topics]:
                        if isinstance(topic_data, dict):
                            topic = BrainstormTopic(
                                title=topic_data.get("title", ""),
                                description=topic_data.get("description", ""),
                                category=topic_data.get("category", ""),
                                relevance_score=0.8,  # 默认相关性分数
                                novelty_score=topic_data.get("novelty_score", 0.5),
                                engagement_potential=topic_data.get("engagement_potential", 0.5),
                                reasoning=topic_data.get("reasoning", ""),
                                tags=topic_data.get("tags", []) if isinstance(topic_data.get("tags"), list) else [],
                            )
                            topics.append(topic)

                    if topics:
                        logger.info(f"[A_Mind] 头脑风暴生成完成，生成{len(topics)}个话题")
                        return topics
                    else:
                        logger.warning("[A_Mind] 解析后的topics列表为空")
                        return self._generate_fallback_topics(context, num_topics)

                except json.JSONDecodeError as e:
                    logger.warning(f"头脑风暴LLM返回的不是有效JSON (解析错误: {e}): {response[:200]}...")
                    return self._generate_fallback_topics(context, num_topics)
                except Exception as e:
                    logger.warning(f"头脑风暴JSON解析异常: {e}, 响应内容: {response[:200]}...")
                    return self._generate_fallback_topics(context, num_topics)

            except Exception as e:
                logger.error(f"LLM头脑风暴生成调用失败: {e}")
                return self._generate_fallback_topics(context, num_topics)

        except Exception as e:
            logger.error(f"头脑风暴生成失败: {e}")
            return []

    def _format_search_results(self, search_results: List[SearchResult]) -> str:
        """格式化搜索结果"""
        if not search_results:
            return "暂无搜索结果"

        formatted = []
        for result in search_results[:3]:  # 只使用前3个结果
            formatted.append(f"- {result.title}: {result.snippet[:100]}...")

        return "\n".join(formatted)

    def _format_knowledge_results(self, knowledge_results: List[KnowledgeItem]) -> str:
        """格式化知识库结果"""
        if not knowledge_results:
            return "暂无知识库内容"

        formatted = []
        for item in knowledge_results[:3]:  # 只使用前3个结果
            formatted.append(f"- {item.title}: {item.content[:100]}...")

        return "\n".join(formatted)

    def _generate_fallback_topics(self, context: Dict[str, Any], num_topics: int) -> List[BrainstormTopic]:
        """备用话题生成方法（当LLM不可用时）"""
        try:
            # 提供更丰富和多样化的兜底话题
            fallback_topic_templates = [
                # 通用话题模板
                {
                    "title": "今天的心情怎么样？",
                    "description": "分享一下最近的心情和生活状态",
                    "category": "生活分享",
                    "tags": ["心情", "生活", "分享"],
                    "engagement_potential": 0.8,
                },
                {
                    "title": "有什么有趣的发现吗？",
                    "description": "分享最近发现的有趣事物、新奇知识或趣闻",
                    "category": "趣闻分享",
                    "tags": ["趣闻", "发现", "分享"],
                    "engagement_potential": 0.7,
                },
                {
                    "title": "最近在学习什么？",
                    "description": "交流学习经历、分享学习资源和方法",
                    "category": "学习交流",
                    "tags": ["学习", "资源", "方法"],
                    "engagement_potential": 0.6,
                },
                {
                    "title": "未来的规划和梦想",
                    "description": "聊聊对未来的规划、职业发展或个人梦想",
                    "category": "规划讨论",
                    "tags": ["规划", "梦想", "未来"],
                    "engagement_potential": 0.7,
                },
                {
                    "title": "推荐一部电影或书籍",
                    "description": "分享最近看过的好电影或读过的好书",
                    "category": "文化推荐",
                    "tags": ["电影", "书籍", "推荐"],
                    "engagement_potential": 0.8,
                },
                {
                    "title": "工作中的趣事",
                    "description": "分享工作中发生的趣事或经验教训",
                    "category": "工作分享",
                    "tags": ["工作", "趣事", "经验"],
                    "engagement_potential": 0.6,
                },
                {
                    "title": "周末计划分享",
                    "description": "聊聊周末的计划安排和期待",
                    "category": "周末话题",
                    "tags": ["周末", "计划", "期待"],
                    "engagement_potential": 0.5,
                },
                {
                    "title": "技术发展趋势探讨",
                    "description": "讨论当前热门技术趋势和未来发展",
                    "category": "技术讨论",
                    "tags": ["技术", "趋势", "未来"],
                    "engagement_potential": 0.7,
                },
            ]

            # 随机选择话题
            selected_templates = random.sample(fallback_topic_templates, min(num_topics, len(fallback_topic_templates)))

            topics = []
            for template in selected_templates:
                topic = BrainstormTopic(
                    title=template["title"],
                    description=template["description"],
                    category=template["category"],
                    relevance_score=0.7,  # 兜底话题给较高相关性
                    novelty_score=0.6,  # 兜底话题有一定新颖性
                    engagement_potential=template["engagement_potential"],
                    reasoning="从多样化话题库中选择的兜底话题",
                    tags=template["tags"],
                )
                topics.append(topic)

            # 如果需要更多话题，补充通用话题
            while len(topics) < num_topics:
                fallback_topic = BrainstormTopic(
                    title="来聊聊最近的新闻吧",
                    description="分享和讨论最近的热门新闻或社会事件",
                    category="新闻讨论",
                    relevance_score=0.5,
                    novelty_score=0.5,
                    engagement_potential=0.6,
                    reasoning="补充的通用兜底话题",
                    tags=["新闻", "讨论", "时事"],
                )
                topics.append(fallback_topic)

            logger.info(f"[A_Mind] 备用方法生成{len(topics)}个多样化话题")
            return topics

        except Exception as e:
            logger.error(f"备用话题生成失败: {e}")
            return []

    def _get_system_personality(self) -> str:
        """获取系统人设信息"""
        try:
            # 获取全局人设配置
            personality_config = global_config.personality

            personality_parts = []

            # 基础人设
            if personality_config.personality:
                personality_parts.append(f"人设：{personality_config.personality}")

            # 回复风格
            if personality_config.reply_style:
                personality_parts.append(f"表达风格：{personality_config.reply_style}")

            # 说话规则
            if personality_config.plan_style:
                personality_parts.append(f"行为规则：{personality_config.plan_style}")

            # 如果都没有，返回默认人设
            if not personality_parts:
                return "我是一个在读大学生，现在正在上网和群友聊天"

            return "；".join(personality_parts)

        except Exception as e:
            logger.warning(f"获取系统人设失败: {e}")
            return "我是一个在读大学生，现在正在上网和群友聊天"

    def _generate_fallback_topics_from_config(self, num_topics: int, context: Dict[str, Any]) -> List[BrainstormTopic]:
        """从配置文件生成兜底话题"""
        try:
            fallback_topics = self.config.get(
                "auto_initiate.fallback_topics",
                [
                    "让我们来聊聊人工智能的发展现状吧",
                    "最近有什么有趣的技术新闻吗？",
                    "分享一下你对未来科技的看法",
                    "今天的心情怎么样？",
                    "有什么好的学习资源推荐吗？",
                ],
            )

            topics = []
            for i in range(min(num_topics, len(fallback_topics))):
                topic_content = fallback_topics[i]

                # 分析话题内容，提取标题和描述
                if "：" in topic_content:
                    title, description = topic_content.split("：", 1)
                else:
                    title = topic_content
                    description = f"讨论{topic_content}"

                topic = BrainstormTopic(
                    title=title.strip(),
                    description=description.strip(),
                    category="兜底话题",
                    relevance_score=0.7,  # 兜底话题给中等相关性分数
                    novelty_score=0.6,  # 兜底话题有一定新颖性
                    engagement_potential=0.7,  # 兜底话题通常有较好参与度
                    reasoning="从配置文件加载的兜底话题",
                    tags=["兜底", "通用", "友好"],
                )
                topics.append(topic)

            # 如果配置文件话题不够，补充通用话题
            while len(topics) < num_topics:
                fallback_topic = BrainstormTopic(
                    title="来聊聊最近的趣事吧",
                    description="分享一下最近发生的有趣事情",
                    category="通用话题",
                    relevance_score=0.5,
                    novelty_score=0.5,
                    engagement_potential=0.6,
                    reasoning="补充的通用兜底话题",
                    tags=["通用", "聊天"],
                )
                topics.append(fallback_topic)

            logger.info(f"[A_Mind] 从配置文件生成{len(topics)}个兜底话题")
            return topics

        except Exception as e:
            logger.error(f"生成配置文件兜底话题失败: {e}")
            return self._generate_fallback_topics(context, num_topics)

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
