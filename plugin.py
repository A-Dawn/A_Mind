"""
重构后的A_Mind插件主文件

使用新的模块化架构
"""

import asyncio
import json
import math
import re
import time
from pathlib import Path
from typing import List, Tuple, Type, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict

# 中文分词支持
try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

# 信息检索相关导入
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseCommand,
    BaseEventHandler,
    ComponentInfo,
    CommandInfo,
    ComponentType,
    ActionActivationType,
    EventType,
    ConfigField,
    MaiMessages,
    ReplyContentType,
)
from src.plugin_system.apis import llm_api, generator_api
from src.plugin_system.apis.llm_api import get_available_models
from src.common.logger import get_logger
from src.config.config import global_config
from src.manager.async_task_manager import AsyncTask, async_task_manager

# 导入重构后的模块
from .core.dependency_container import DependencyContainer
from .core.config_manager import ConfigManager
from .core.permissions import PermissionManager
from .models import *
from .services import *
from .commands import *
from .handlers import *
from .repositories.database_manager import DatabaseManager
from .database import init_database
from .utils import get_global_db_manager

# 获取日志器
logger = get_logger("A_Mind")

# 全局插件实例，用于权限检查装饰器
_plugin_instance = None


def require_permission(permission_level: str = "admin"):
    """权限检查装饰器"""

    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # 从参数中提取用户ID
            user_id = None
            if hasattr(self, 'container') and self.container:
                # 尝试从命令上下文中获取用户ID
                # 这里需要根据实际的命令处理逻辑来调整
                pass

            # 如果无法获取用户ID，允许执行（向后兼容）
            if user_id is None:
                return await func(self, *args, **kwargs)

            # 权限检查
            if not self.container.permission_manager.has_permission(user_id, permission_level):
                return False, f"权限不足：需要 {permission_level} 权限", False

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


@register_plugin
class AMindPlugin(BasePlugin):
    """A_Mind智能话题管理插件 - 重构版本"""

    # 插件基本信息
    plugin_name = "a_mind"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 设置全局插件实例
        global _plugin_instance
        _plugin_instance = self

        # 初始化依赖注入容器
        self.container = DependencyContainer(self)

        # 向后兼容：设置全局数据库管理器
        global _db_manager_instance
        _db_manager_instance = self.container.database_manager

        # 插件初始化时执行数据库架构迁移
        try:
            if hasattr(self.container.database_manager, 'migrate_database_schema'):
                success = self.container.database_manager.migrate_database_schema()
                if success:
                    logger.info("[A_Mind] 数据库架构迁移成功")
                else:
                    logger.warning("[A_Mind] 数据库架构迁移失败")
        except Exception as e:
            logger.error(f"[A_Mind] 插件初始化异常: {e}")

    # 配置Schema定义（保持与原版本兼容）
    # 基础配置schema（不包含动态plan）
    _base_config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=False, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="1.0.0", description="配置文件版本"),
        },
        "permissions": {
            "super_admins": ConfigField(type=list, default=[""], description="超级管理员用户ID列表"),
            "admin_groups": ConfigField(type=list, default=[""], description="管理员群组ID列表"),
            "enable_inheritance": ConfigField(type=bool, default=True, description="启用权限继承机制"),
            "inheritance_controlled_by_user": ConfigField(type=bool, default=True, description="继承由用户控制聊天流"),
            "global_admin_mode": ConfigField(
                type=bool, default=False, description="全局管理员模式 - 开启后所有用户均为管理员"
            ),
        },
        "debug": {
            "enable_debug_mode": ConfigField(type=bool, default=False, description="启用调试模式"),
            "debug_command_prefix": ConfigField(type=str, default="/amind_debug", description="调试命令前缀"),
            "allowed_debug_users": ConfigField(
                type=list, default=["123456789"], description="允许使用调试功能的用户ID"
            ),
        },
        "llm": {
            "use_builtin": ConfigField(type=bool, default=True, description="固定为true，使用内置LLM"),
            "model_name": ConfigField(
                type=str, default="utils", description="模型选择：utils/replyer/planner"
            ),
            "fallback_openai": ConfigField(type=bool, default=False, description="是否启用OpenAI作为备选"),
            "openai_api_key": ConfigField(type=str, default="", description="OpenAI备用API密钥"),
            "fallback_model_name": ConfigField(
                type=str, default="replyer", description="备选模型名称（当首选模型失败时使用）"
            ),
            "temperature": ConfigField(type=float, default=0.7, description="生成温度"),
            "max_tokens": ConfigField(type=int, default=1500, description="最大token数"),
        },
        "services": {
            "brainstorm": {
                "model_name": ConfigField(
                    type=str, default="utils", description="头脑风暴专用模型（空表示使用全局默认）"
                ),
                "fallback_model_name": ConfigField(
                    type=str, default="replyer", description="头脑风暴备选模型（空表示使用全局默认）"
                ),
                "temperature": ConfigField(type=float, default=0.8, description="头脑风暴生成温度（0.8适合创意生成）"),
                "max_tokens": ConfigField(type=int, default=2000, description="头脑风暴最大token数"),
            },
            "decision": {
                "model_name": ConfigField(
                    type=str, default="planner", description="决策选择专用模型（空表示使用全局默认）"
                ),
                "fallback_model_name": ConfigField(
                    type=str, default="utils", description="决策选择备选模型（空表示使用全局默认）"
                ),
                "temperature": ConfigField(type=float, default=0.3, description="决策选择生成温度（0.3适合分析决策）"),
                "max_tokens": ConfigField(type=int, default=1000, description="决策选择最大token数"),
            },
        },
        "prompts": {
            "matching_system_prompt": ConfigField(
                type=str, default="你是一个话题匹配专家，负责分析消息内容与话题描述的相关性。请返回一个0-1之间的匹配分数。重要：只返回一个小数数字，不要包含任何解释、思考过程或其他文本。例如：0.85", description="匹配分析系统提示词"
            ),
            "initiate_brainstorm_prompt": ConfigField(
                type=str, default="请基于以下信息进行头脑风暴，生成{num_topics}个相关的话题建议：\n\n上下文信息：\n- 原始话题：{original_topic}\n- 描述：{description}\n- 相关搜索结果：{search_results}\n- 知识库内容：{knowledge_content}\n\n要求：\n1. 每个话题都要有创新性和吸引力\n2. 话题应该与原始主题相关但不重复\n3. 考虑用户参与度和讨论潜力\n4. 提供简洁有力的标题和描述\n5. 为每个话题添加合适的标签\n\n请严格返回JSON格式，不要输出任何其他内容：\n{{\n  \"topics\": [\n    {{\n      \"title\": \"话题标题\",\n      \"description\": \"话题描述（50字以内）\",\n      \"category\": \"话题分类\",\n      \"novelty_score\": 0.0,\n      \"engagement_potential\": 0.0,\n      \"reasoning\": \"生成理由\",\n      \"tags\": [\"标签1\", \"标签2\"]\n    }}\n  ]\n}}\n", description="自发起头脑风暴提示词"
            ),
            "initiate_decision_prompt": ConfigField(
                type=str, default="请从以下话题选项中选择最适合发起讨论的一个：\n\n原始话题：{original_topic}\n当前参与情况：{engagement_context}\n\n候选话题列表：\n{topic_list}\n\n选择标准：\n1. 相关性：与原始话题的相关程度\n2. 新颖性：话题的新鲜感和吸引力\n3. 参与潜力：能够激发用户讨论的可能性\n4. 时机合适性：当前是否是讨论的好时机\n5. 多样性：避免与现有话题过度重复\n\n请返回JSON格式：\n{{\n  \"selected_index\": 0,\n  \"confidence_score\": 0.0,\n  \"reasoning\": \"选择理由\",\n  \"criteria_scores\": {{\n    \"relevance\": 0.0,\n    \"novelty\": 0.0,\n    \"engagement_potential\": 0.0,\n    \"timing\": 0.0,\n    \"diversity\": 0.0\n  }}\n}}\n", description="自发起决策提示词"
            ),
            "evaluation_prompt": ConfigField(type=str, default="请评估以下话题的进展情况和用户参与度：\n\n话题信息：\n标题：{title}\n描述：{description}\n创建时间：{created_time}\n最后活动：{last_activity}\n回复数量：{reply_count}\n参与度分数：{engagement_score}\n\n最近回复：\n{recent_messages}\n\n请从以下维度进行评估：\n1. 用户参与度 (0-1)：活跃度、回复频率、用户多样性\n2. 话题进展度 (0-1)：是否达成预期目标、讨论深度\n3. 对话健康度 (0-1)：积极正面、建设性讨论\n\n请返回JSON格式：\n{{\n  \"engagement_score\": 0.0,\n  \"progress_score\": 0.0,\n  \"sentiment_score\": 0.0,\n  \"recommendation\": \"continue/pause/terminate/initiate\",\n  \"reason\": \"评估理由\"\n}}\n", description="进展评估提示词"),
            "visibility_analysis_prompt": ConfigField(
                type=str, default="分析以下话题的参与情况，判断应该保持公开还是转为私有：\n{topic_info}\n请给出可见性建议和原因。", description="可见性分析提示词"
            ),
        },
        "topic_management": {
            "max_active_topics": ConfigField(type=int, default=5, description="最大同时活跃话题数"),
            "max_topic_duration_days": ConfigField(type=int, default=7, description="话题最大持续时间"),
            "auto_archive_days": ConfigField(type=int, default=30, description="自动归档时间"),
            "default_visibility": ConfigField(
                type=str, default="public", description="默认可见性：public(公开)/private(私有)"
            ),
            "force_visibility": ConfigField(
                type=str, default="", description="强制可见性：空表示不强制，否则为public/private"
            ),
            "enable_auto_visibility_change": ConfigField(
                type=bool, default=True, description="启用自动可见性转换（由大模型决定）"
            ),
            "auto_initiate_interval_hours": ConfigField(type=int, default=24, description="自发起检查间隔（小时）"),
            "auto_initiate_max_attempts": ConfigField(type=int, default=3, description="单个话题最大自发起次数"),
        },
        "matching": {
            "similarity_threshold": ConfigField(type=float, default=0.6, description="LLM匹配相似度阈值"),
            "keyword_boost": ConfigField(type=float, default=1.2, description="关键词匹配权重"),
            "context_window": ConfigField(type=int, default=15, description="上下文消息窗口大小"),
            "time_decay_factor": ConfigField(type=float, default=0.95, description="时间衰减因子"),
        },
        "state_check": {
            "check_interval_minutes": ConfigField(type=int, default=20, description="状态检查间隔（分钟）"),
            "min_replies_for_check": ConfigField(type=int, default=5, description="触发检查的最小回复数"),
            "engagement_threshold": ConfigField(type=float, default=0.3, description="用户参与度阈值"),
            "enable_termination_detection": ConfigField(
                type=bool, default=True, description="启用用户终止意图检测功能"
            ),
        },
        "auto_initiate": {
            "enable_personality_injection": ConfigField(
                type=bool, default=True, description="是否在自发起话题中注入系统人设"
            ),
            "initiate_strategy": ConfigField(
                type=str, default="balanced", description="自发起策略：creation_only/activation_only/balanced/random"
            ),
            "creation_probability": ConfigField(
                type=float, default=0.6, description="创建新话题的概率（0.0-1.0），仅在balanced模式下使用"
            ),
            "creation_based_on_search": ConfigField(
                type=bool, default=True, description="是否基于互联网搜索创建新话题"
            ),
            "min_search_results": ConfigField(type=int, default=5, description="最少需要多少搜索结果才创建话题"),
            "search_keywords": ConfigField(
                type=list, default=["社会热点新闻", "娱乐八卦资讯", "美食推荐攻略", "旅游景点介绍", "电影电视剧推荐", "音乐新歌榜单", "游戏行业动态", "时尚潮流趋势", "健康生活指南", "育儿教育经验", "职场发展建议", "投资理财知识", "家居装修灵感", "宠物养护知识", "运动健身方法", "心理健康话题", "文化艺术资讯", "生活小技巧"], description="基础搜索关键词列表"
            ),
            "tech_keywords": ConfigField(
                type=list, default=["AI应用", "智能手机", "社交媒体", "移动支付", "在线教育", "远程办公", "直播技术", "短视频平台", "云计算服务", "大数据应用", "网络安全", "数字创新"], description="技术类关键词列表"
            ),
            "science_keywords": ConfigField(
                type=list, default=["医学健康", "营养饮食", "环境保护", "气候变化", "新能源应用", "太空探索", "基因科技", "大脑科学", "生命科学", "材料创新"], description="科学类关键词列表"
            ),
            "social_keywords": ConfigField(
                type=list, default=["社会热点", "教育话题", "医疗健康", "经济新闻", "文化传承", "城市生活", "乡村发展", "创业就业", "青年话题", "家庭教育", "养老保障", "住房政策", "交通出行", "社区生活", "公益活动", "志愿服务", "传统文化", "现代生活", "消费趋势", "社交关系"], description="社会类关键词列表"
            ),
            "entertainment_keywords": ConfigField(
                type=list, default=["娱乐新闻", "电影推荐", "电视剧追剧", "音乐新歌", "综艺节目", "明星八卦", "体育赛事", "游戏攻略", "动漫新作", "短视频热点", "直播精彩", "电竞比赛", "时尚穿搭", "美妆护肤", "美食探店", "旅游攻略", "摄影技巧", "手工DIY", "创意设计", "艺术展览"], description="娱乐类关键词列表"
            ),
            "activation_priority": ConfigField(
                type=str, default="engagement", description="启动优先级：engagement/recency/random"
            ),
            "min_engagement_for_activation": ConfigField(
                type=float, default=0.4, description="启动话题的最小参与度阈值"
            ),
            "max_topics_to_consider": ConfigField(type=int, default=10, description="考虑启动的最大话题数量"),
            "default_stream_config": ConfigField(
                type=str, default="", description="默认聊天流配置，格式同plan1.stream_config"
            ),
            "fallback_topics": ConfigField(
                type=list,
                default=["大家玩原神吗？"],
                description="兜底话题列表，当LLM生成失败时使用",
            ),
            "fallback_topic_probability": ConfigField(
                type=float, default=0.0, description="使用兜底话题的概率（0.0-1.0），用于增加话题多样性"
            ),
        },
        "internet_search": {
            "engine": ConfigField(
                type=str, default="tavily", description="搜索引擎选择：tavily/duckduckgo/searxng"
            ),
            "tavily_api_key": ConfigField(type=str, default="", description="Tavily API密钥"),
            "tavily_base_url": ConfigField(type=str, default="https://api.tavily.com", description="Tavily API基础URL"),
            "searxng_base_url": ConfigField(type=str, default="", description="SearXNG实例URL"),
            "timeout": ConfigField(type=int, default=15, description="搜索请求超时时间（秒）"),
            "max_results": ConfigField(type=int, default=5, description="最大搜索结果数量"),
        },
        # 多Plan配置支持：支持 plan1, plan2, plan3... 任意多个计划
        # 每个plan可以独立配置不同的聊天流、触发概率、间隔时间等
        # 示例：在config.toml中添加 [plan2], [plan3] 等配置段即可
        "plan1": {
            "enabled": ConfigField(
                type=bool, default=False, description="Plan-1：是否启用短周期 tick + 概率触发自动发起"
            ),
            "stream_config": ConfigField(
                type=str, default="qq:1145141919810:group", description="Plan-1：目标聊天流配置，如 qq:123456:group"
            ),
            "tick_interval_seconds": ConfigField(type=int, default=120, description="Plan-1：tick 周期（秒）"),
            "trigger_probability": ConfigField(type=float, default=0.2, description="Plan-1：每 tick 触发概率（0-1）"),
            "cooldown_seconds": ConfigField(type=int, default=1800, description="Plan-1：触发冷却（秒）"),
        },
        "plan2": {
            "enabled": ConfigField(
                type=bool, default=False, description="Plan-2：是否启用短周期 tick + 概率触发自动发起"
            ),
            "stream_config": ConfigField(
                type=str, default="qq:1145141919811:private", description="Plan-2：目标聊天流配置，如 qq:123456:group"
            ),
            "tick_interval_seconds": ConfigField(type=int, default=120, description="Plan-2：tick 周期（秒）"),
            "trigger_probability": ConfigField(type=float, default=0.2, description="Plan-2：每 tick 触发概率（0-1）"),
            "cooldown_seconds": ConfigField(type=int, default=1800, description="Plan-2：触发冷却（秒）"),
        },
    }

    @property
    def config_schema(self):
        """动态生成包含所有plan的配置schema"""
        # 复制基础schema
        schema = self._base_config_schema.copy()

        # 动态添加所有plan配置
        try:
            # 尝试从配置文件读取所有plan
            config_path = self.plugin_dir / "config.toml"
            if config_path.exists():
                import toml
                config = toml.load(config_path)
                for key in config.keys():
                    if key.startswith('plan') and isinstance(config[key], dict):
                        # 为每个plan生成schema
                        plan_num = key.replace('plan', '') if key != 'plan' else '1'
                        schema[key] = {
                            "enabled": ConfigField(
                                type=bool, default=False,
                                description=f"Plan-{plan_num}：是否启用短周期 tick + 概率触发自动发起"
                            ),
                            "stream_config": ConfigField(
                                type=str, default="",
                                description=f"Plan-{plan_num}：目标聊天流配置，如 qq:123456:group"
                            ),
                            "tick_interval_seconds": ConfigField(
                                type=int, default=30,
                                description=f"Plan-{plan_num}：tick 周期（秒）"
                            ),
                            "trigger_probability": ConfigField(
                                type=float, default=0.02,
                                description=f"Plan-{plan_num}：每 tick 触发概率（0-1）"
                            ),
                            "cooldown_seconds": ConfigField(
                                type=int, default=1800,
                                description=f"Plan-{plan_num}：触发冷却（秒）"
                            ),
                            "model_config": {
                                "model_name": ConfigField(
                                    type=str, default="",
                                    description=f"Plan-{plan_num}：专用模型（空表示使用全局默认）"
                                ),
                                "fallback_model_name": ConfigField(
                                    type=str, default="",
                                    description=f"Plan-{plan_num}：备选模型（空表示使用全局默认）"
                                ),
                                "temperature": ConfigField(
                                    type=float, default=0.7,
                                    description=f"Plan-{plan_num}：生成温度"
                                ),
                                "max_tokens": ConfigField(
                                    type=int, default=1500,
                                    description=f"Plan-{plan_num}：最大token数"
                                ),
                            },
                            "services": {
                                "brainstorm": {
                                    "model_name": ConfigField(
                                        type=str, default="",
                                        description=f"Plan-{plan_num}：头脑风暴专用模型（空表示使用上级配置）"
                                    ),
                                    "fallback_model_name": ConfigField(
                                        type=str, default="",
                                        description=f"Plan-{plan_num}：头脑风暴备选模型（空表示使用上级配置）"
                                    ),
                                    "temperature": ConfigField(
                                        type=float, default=0.8,
                                        description=f"Plan-{plan_num}：头脑风暴生成温度"
                                    ),
                                    "max_tokens": ConfigField(
                                        type=int, default=2000,
                                        description=f"Plan-{plan_num}：头脑风暴最大token数"
                                    ),
                                },
                                "decision": {
                                    "model_name": ConfigField(
                                        type=str, default="",
                                        description=f"Plan-{plan_num}：决策选择专用模型（空表示使用上级配置）"
                                    ),
                                    "fallback_model_name": ConfigField(
                                        type=str, default="",
                                        description=f"Plan-{plan_num}：决策选择备选模型（空表示使用上级配置）"
                                    ),
                                    "temperature": ConfigField(
                                        type=float, default=0.3,
                                        description=f"Plan-{plan_num}：决策选择生成温度"
                                    ),
                                    "max_tokens": ConfigField(
                                        type=int, default=1000,
                                        description=f"Plan-{plan_num}：决策选择最大token数"
                                    ),
                                },
                            },
                        }
        except Exception:
            # 如果无法读取配置文件，使用默认的plan1和plan2
            pass

        return schema

    async def on_load(self):
        """插件加载时的初始化"""
        try:
            # 初始化数据库表
            init_database()
            logger.info("A_Mind插件重构版本加载完成")
        except Exception as e:
            logger.error(f"A_Mind插件加载失败: {e}")
            raise

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""
        return [
            # 命令组件
            (CreateTopicCommand.get_command_info(), CreateTopicCommand),
            (ListTopicsCommand.get_command_info(), ListTopicsCommand),
            (UpdateTopicCommand.get_command_info(), UpdateTopicCommand),
            (DeleteTopicCommand.get_command_info(), DeleteTopicCommand),
            (VisibilityCommand.get_command_info(), VisibilityCommand),
            (StreamManagementCommand.get_command_info(), StreamManagementCommand),
            (CheckCommand.get_command_info(), CheckCommand),
            (InitiateCommand.get_command_info(), InitiateCommand),
            (HelpCommand.get_command_info(), HelpCommand),
            (DebugCommand.get_command_info(), DebugCommand),
            (ModelConfigCommand.get_command_info(), ModelConfigCommand),
            # 事件处理器组件
            (AMindStartHandler.get_handler_info(), AMindStartHandler),
            (MessageTrackerEventHandler.get_handler_info(), MessageTrackerEventHandler),
            (StateCheckAction.get_action_info(), StateCheckAction),
            (AutoInitiateAction.get_action_info(), AutoInitiateAction),
        ]


# get_global_db_manager现在在utils.py中定义
