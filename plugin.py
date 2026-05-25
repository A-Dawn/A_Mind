"""
A_Mind插件主文件
"""

import asyncio
import contextlib
import importlib
import json
import math
import re
import sys
import time
from types import SimpleNamespace
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
from .core.amind_logger import get_logger
from src.config.config import global_config
from src.manager.async_task_manager import AsyncTask, async_task_manager

from maibot_sdk import MaiBotPlugin
from maibot_sdk.compat import _context_holder

# 导入重构后的模块
from .core.dependency_container import DependencyContainer
from .core.config_manager import ConfigManager
from .core.permissions import PermissionManager
from .models import *
from .services import *
from .commands import *
from .commands.keyword_weights_command import KeywordWeightsCommand
from .handlers import *
from .repositories.database_manager import DatabaseManager
from .database import init_database
from .utils import get_global_db_manager

# 获取日志器
logger = get_logger(__name__)

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
        # 首先调用父类初始化
        super().__init__(*args, **kwargs)
        self.plugin_dir = Path(__file__).parent
        self._plugin_config: Dict[str, Any] = {}

        # 设置全局插件实例
        global _plugin_instance
        _plugin_instance = self

        # 初始化依赖注入容器（先创建容器，这样才有config_manager）
        self.container = DependencyContainer(self)

        # ===== 然后初始化日志管理器（使用容器中的config_manager）=====
        self._init_logger_manager()

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

    def set_plugin_config(self, config: Dict[str, Any]) -> None:
        self._plugin_config = config if isinstance(config, dict) else {}

    def get_config(self, key: str, default: Any = None) -> Any:
        value = _get_nested_config(self._plugin_config, key, None)
        if value is not None:
            return value
        try:
            import toml

            config_path = self.plugin_dir / "config.toml"
            if config_path.exists():
                return _get_nested_config(toml.load(config_path), key, default)
        except Exception:
            pass
        return default

    def _init_logger_manager(self):
        """初始化日志管理器（在容器创建后执行）"""
        try:
            from .core.amind_logger import AMindLogger, set_amind_logger, get_logger

            # 创建日志管理器（使用容器中的config_manager）
            logger_mgr = AMindLogger(self.container.config_manager)
            set_amind_logger(logger_mgr)

            # 使用新的logger记录初始化
            init_logger = get_logger("plugin")
            init_logger.info("[A_Mind] 日志管理器初始化完成")

        except Exception as e:
            # 如果日志管理器初始化失败，使用默认logger记录错误
            import traceback
            from src.common.logger import get_logger as base_get_logger
            fallback_logger = base_get_logger("A_Mind")
            fallback_logger.error(f"[A_Mind] 日志管理器初始化失败: {e}")
            fallback_logger.error(f"[A_Mind] 错误详情: {traceback.format_exc()}")

    # 配置Schema定义（保持与原版本兼容）
    # 基础配置schema（不包含动态plan）
    _base_config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=False, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="2.0.0", description="配置文件版本"),
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
        "logging": {
            # ===== 总体控制 =====
            "enabled": ConfigField(type=bool, default=True, description="是否启用日志输出（完全禁用A_Mind所有日志）"),
            # ===== 预设模式（提供合理的默认值）=====
            "preset": ConfigField(
                type=str, default="normal",
                description="日志预设模式：minimal(最小)/normal(正常)/verbose(详细)/debug(调试)",
                choices=["minimal", "normal", "verbose", "debug"]
            ),
            # ===== 全局级别（可覆盖预设）=====
            "level": ConfigField(
                type=str, default="INHERIT",
                description="全局日志级别（INHERIT表示使用预设值）",
                choices=["INHERIT", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
            ),
            # ===== 模块级别控制（可覆盖全局级别）=====
            "modules": {
                "services": ConfigField(
                    type=str, default="INHERIT",
                    description="服务层日志级别（INHERIT表示继承上级配置）",
                    choices=["INHERIT", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "OFF"]
                ),
                "handlers": ConfigField(
                    type=str, default="INHERIT",
                    description="处理器层日志级别（INHERIT表示继承上级配置）",
                    choices=["INHERIT", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "OFF"]
                ),
                "commands": ConfigField(
                    type=str, default="INHERIT",
                    description="命令层日志级别（INHERIT表示继承上级配置）",
                    choices=["INHERIT", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "OFF"]
                ),
                "core": ConfigField(
                    type=str, default="INHERIT",
                    description="核心模块日志级别（INHERIT表示继承上级配置）",
                    choices=["INHERIT", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "OFF"]
                ),
                "database": ConfigField(
                    type=str, default="INHERIT",
                    description="数据库日志级别（INHERIT表示继承上级配置）",
                    choices=["INHERIT", "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "OFF"]
                ),
            },
            # ===== 特定功能开关 =====
            "features": {
                "show_search_results": ConfigField(
                    type=bool, default=False, description="显示搜索结果详情（通常输出较多）"
                ),
                "show_llm_prompts": ConfigField(
                    type=bool, default=False, description="显示LLM提示词（通常很长）"
                ),
                "show_topic_matching": ConfigField(
                    type=bool, default=False, description="显示话题匹配详情"
                ),
                "show_initiation_workflow": ConfigField(
                    type=bool, default=False, description="显示自发起工作流详细步骤"
                ),
                "show_performance_metrics": ConfigField(
                    type=bool, default=False, description="显示性能指标（耗时、计数等）"
                ),
            },
            # ===== 输出格式控制 =====
            "format": {
                "show_timestamp": ConfigField(
                    type=bool, default=False, description="显示时间戳"
                ),
                "show_module_name": ConfigField(
                    type=bool, default=False, description="显示模块名称"
                ),
                "use_colors": ConfigField(
                    type=bool, default=True, description="使用彩色输出（终端支持时）"
                ),
                "compact_mode": ConfigField(
                    type=bool, default=True, description="紧凑模式（减少空白行）"
                ),
            },
            # ===== 文件输出（可选）=====
            "file_output": {
                "enabled": ConfigField(
                    type=bool, default=False, description="启用日志文件输出"
                ),
                "path": ConfigField(
                    type=str, default="logs/amind.log", description="日志文件路径"
                ),
                "max_size_mb": ConfigField(
                    type=int, default=10, description="单个日志文件最大大小（MB）"
                ),
                "backup_count": ConfigField(
                    type=int, default=5, description="保留的日志文件备份数量"
                ),
            },
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
            # 免打扰设置
            "dnd_enabled": ConfigField(type=bool, default=False, description="是否启用免打扰模式"),
            "dnd_start_time": ConfigField(type=str, default="23:00", description="免打扰开始时间 (HH:MM)"),
            "dnd_end_time": ConfigField(type=str, default="08:00", description="免打扰结束时间 (HH:MM)"),
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
            "exploration_epsilon": ConfigField(
                type=float, default=0.2, description="探索因子：以该概率忽略历史偏好，进行随机探索 (0.0 - 1.0)"
            ),
            "enable_dynamic_queries": ConfigField(
                type=bool, default=True, description="启用动态查询生成：使用LLM将宽泛关键词转化为具体时效性查询"
            ),
        },
        "internet_search": {
            "engine": ConfigField(
                type=str, default="tavily", description="搜索引擎选择：tavily/duckduckgo/searxng"
            ),
            "tavily_api_key": ConfigField(type=list, default=[], description="Tavily API密钥 (支持单个字符串或密钥列表)"),
            "tavily_base_url": ConfigField(type=str, default="https://api.tavily.com", description="Tavily API基础URL"),
            "searxng_base_url": ConfigField(type=str, default="", description="SearXNG实例URL"),
            "timeout": ConfigField(type=int, default=15, description="搜索请求超时时间（秒）"),
            "max_results": ConfigField(type=int, default=5, description="最大搜索结果数量"),
        },
        "global_pool": {
            "enabled": ConfigField(type=bool, default=False, description="是否启用总控池主动话题"),
            "whitelist_streams": ConfigField(type=list, default=[], description="总控池白名单流ID列表"),
            "tick_interval_seconds": ConfigField(type=int, default=300, description="总控池扫描周期（秒）"),
            "lookback_hours": ConfigField(type=int, default=12, description="回看消息窗口（小时）"),
            "min_messages_for_analysis": ConfigField(type=int, default=20, description="触发分析所需最小消息量"),
            "summary_retention_hours": ConfigField(type=int, default=72, description="摘要保留时长（小时）"),
            "raw_retention_hours": ConfigField(type=int, default=24, description="原文保留时长（小时）"),
            "default_policy_profile": ConfigField(
                type=str,
                default="conservative",
                choices=["conservative", "balanced", "aggressive"],
                description="默认策略档位",
            ),
            "per_stream_cooldown_seconds": ConfigField(type=int, default=7200, description="单流冷却（秒）"),
            "global_cooldown_seconds": ConfigField(type=int, default=1800, description="全局冷却（秒）"),
            "max_global_sends_per_day": ConfigField(type=int, default=6, description="全局日发送上限"),
            "max_per_stream_sends_per_day": ConfigField(type=int, default=2, description="单流日发送上限"),
            "enable_cross_stream_boost": ConfigField(type=bool, default=True, description="启用跨流共振加分"),
            "blocked_keywords": ConfigField(type=list, default=[], description="命中即阻断发送的关键词"),
            "stream_policy": ConfigField(
                type=dict,
                default={},
                description="按流映射策略，格式：{stream_id: conservative|balanced|aggressive}",
            ),
            "policy_profiles": {
                "conservative": {
                    "min_decision_score": ConfigField(type=float, default=0.85, description="最低决策分"),
                    "trigger_probability": ConfigField(type=float, default=0.25, description="触发概率"),
                    "min_novelty_score": ConfigField(type=float, default=0.60, description="最低新颖度"),
                    "min_interest_score": ConfigField(type=float, default=0.60, description="最低兴趣度"),
                    "max_candidates_per_tick": ConfigField(type=int, default=2, description="每轮最大候选数"),
                },
                "balanced": {
                    "min_decision_score": ConfigField(type=float, default=0.75, description="最低决策分"),
                    "trigger_probability": ConfigField(type=float, default=0.50, description="触发概率"),
                    "min_novelty_score": ConfigField(type=float, default=0.50, description="最低新颖度"),
                    "min_interest_score": ConfigField(type=float, default=0.50, description="最低兴趣度"),
                    "max_candidates_per_tick": ConfigField(type=int, default=3, description="每轮最大候选数"),
                },
                "aggressive": {
                    "min_decision_score": ConfigField(type=float, default=0.65, description="最低决策分"),
                    "trigger_probability": ConfigField(type=float, default=0.80, description="触发概率"),
                    "min_novelty_score": ConfigField(type=float, default=0.40, description="最低新颖度"),
                    "min_interest_score": ConfigField(type=float, default=0.40, description="最低兴趣度"),
                    "max_candidates_per_tick": ConfigField(type=int, default=5, description="每轮最大候选数"),
                },
            },
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
            "topic_capture": {
                "enabled": ConfigField(
                    type=bool, default=False, description="Plan-1：是否启用话题捕捉"
                ),
                "probability": ConfigField(
                    type=float, default=0.5, description="Plan-1：话题捕捉触发概率 (0.0-1.0)"
                ),
                "interval": ConfigField(
                    type=int, default=600, description="Plan-1：话题捕捉冷却时间（秒）"
                ),
                "min_messages": ConfigField(
                    type=int, default=5, description="Plan-1：触发捕捉所需的最小上下文消息数"
                ),
            },
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
                            "keyword_weights": {
                                "enable_manual_weights": ConfigField(
                                    type=bool, default=False,
                                    description=f"Plan-{plan_num}：是否启用手动权重（覆盖自动分析）"
                                ),
                                "tech_weight": ConfigField(
                                    type=float, default=0.25,
                                    description=f"Plan-{plan_num}：技术类关键词权重（0.0-1.0）"
                                ),
                                "science_weight": ConfigField(
                                    type=float, default=0.25,
                                    description=f"Plan-{plan_num}：科学类关键词权重（0.0-1.0）"
                                ),
                                "social_weight": ConfigField(
                                    type=float, default=0.25,
                                    description=f"Plan-{plan_num}：社会类关键词权重（0.0-1.0）"
                                ),
                                "entertainment_weight": ConfigField(
                                    type=float, default=0.25,
                                    description=f"Plan-{plan_num}：娱乐类关键词权重（0.0-1.0）"
                                ),
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
            (PoolCommand.get_command_info(), PoolCommand),
            (HelpCommand.get_command_info(), HelpCommand),
            (DebugCommand.get_command_info(), DebugCommand),
            (ModelConfigCommand.get_command_info(), ModelConfigCommand),
            (KeywordWeightsCommand.get_command_info(), KeywordWeightsCommand),
            # 事件处理器组件
            (AMindStartHandler.get_handler_info(), AMindStartHandler),
            (MessageTrackerEventHandler.get_handler_info(), MessageTrackerEventHandler),
            (GlobalPoolCollectorEventHandler.get_handler_info(), GlobalPoolCollectorEventHandler),
            (StateCheckAction.get_action_info(), StateCheckAction),
            (AutoInitiateAction.get_action_info(), AutoInitiateAction),
        ]


class AMindSDKPlugin(MaiBotPlugin):
    """MaiBot SDK facade around the existing A_Mind business components."""

    config_reload_subscriptions = ("bot", "model")

    def __init__(self):
        super().__init__()
        self._legacy = AMindPlugin()
        self._component_specs: List[Tuple[ComponentInfo, Type]] = []
        self._component_instances: Dict[str, Any] = {}
        self._component_map: Dict[str, Dict[str, Any]] = {}
        self.plugin_dir = Path(__file__).parent
        _install_legacy_llm_patch()

    def __getattr__(self, name: str):
        prefix = "_amind_dispatch__"
        if name.startswith(prefix):
            component_name = name[len(prefix):]

            async def _handler(**kwargs):
                kwargs["component_name"] = component_name
                component = self._component_map.get(component_name, {})
                component_type = str(component.get("type", "") or "")
                if component_type == "COMMAND":
                    return await self._dispatch_command(**kwargs)
                if component_type == "EVENT_HANDLER":
                    return await self._dispatch_event(**kwargs)
                if component_type in ("ACTION", "TOOL"):
                    return await self._dispatch_action(**kwargs)
                raise KeyError(f"未知 A_Mind 组件: {component_name}")

            return _handler
        raise AttributeError(name)

    def _set_context(self, ctx):
        super()._set_context(ctx)
        _context_holder.set_context(ctx)

    def set_plugin_config(self, config: Dict[str, Any]) -> None:
        super().set_plugin_config(config)
        if hasattr(self._legacy, "set_plugin_config"):
            self._legacy.set_plugin_config(config)

    def get_config(self, key: str, default: Any = None) -> Any:
        return _get_nested_config(self.get_plugin_config_data(), key, default)

    def get_default_config(self) -> Dict[str, Any]:
        try:
            return _schema_to_default_config(self._legacy.config_schema)
        except Exception as exc:
            logger.warning(f"[A_Mind] 生成默认配置失败: {exc}")
            return {}

    def normalize_plugin_config(self, config_data):
        default_config = self.get_default_config()
        normalized = _merge_config(default_config, config_data or {})
        return normalized, normalized != (config_data or {})

    async def on_load(self) -> None:
        await self._legacy.on_load()

    async def on_unload(self) -> None:
        shutdown = getattr(self._legacy, "on_unload", None)
        if callable(shutdown):
            result = shutdown()
            if asyncio.iscoroutine(result):
                await result

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        del version
        if scope == "self":
            self.set_plugin_config(config_data if isinstance(config_data, dict) else {})

    def get_components(self) -> List[Dict[str, Any]]:
        if not self._component_specs:
            self._component_specs = list(self._legacy.get_plugin_components())

        components: List[Dict[str, Any]] = []
        for comp_info, comp_cls in self._component_specs:
            if not getattr(comp_info, "enabled", True):
                continue
            name = str(getattr(comp_info, "name", "") or "").strip()
            if not name:
                continue
            if name not in self._component_instances:
                self._component_instances[name] = comp_cls()
            component = self._convert_component(comp_info, self._component_instances[name])
            if component:
                self._component_map[name] = component
                components.append(component)
        return components

    def _convert_component(self, comp_info: ComponentInfo, instance: Any) -> Optional[Dict[str, Any]]:
        ctype = str(getattr(comp_info, "component_type", "") or "")
        name = str(getattr(comp_info, "name", "") or "").strip()
        description = str(getattr(comp_info, "description", "") or "").strip()

        if ctype == "command":
            return {
                "type": "COMMAND",
                "component_type": "COMMAND",
                "name": name,
                "description": description or getattr(instance, "command_description", ""),
                "metadata": {
                    "command_pattern": getattr(instance, "command_pattern", ""),
                    "handler_name": f"_amind_dispatch__{name}",
                    "legacy": True,
                },
            }
        if ctype == "event_handler":
            return {
                "type": "EVENT_HANDLER",
                "component_type": "EVENT_HANDLER",
                "name": name,
                "description": description or getattr(instance, "handler_description", ""),
                "metadata": {
                    "event_type": str(getattr(instance, "event_type", "on_message")),
                    "weight": int(getattr(instance, "weight", 0)),
                    "intercept_message": bool(getattr(instance, "intercept_message", False)),
                    "handler_name": f"_amind_dispatch__{name}",
                    "legacy": True,
                },
            }
        if ctype == "action":
            parameters = getattr(instance, "action_parameters", {}) or {}
            parameters_schema = _legacy_action_parameters_to_tool_schema(parameters)
            return {
                "type": "TOOL",
                "component_type": "TOOL",
                "name": name,
                "description": description or getattr(instance, "action_description", ""),
                "metadata": {
                    "brief_description": description or getattr(instance, "action_description", "") or name,
                    "detailed_description": _legacy_action_tool_description(instance, parameters_schema),
                    "parameters_raw": parameters_schema,
                    "invoke_method": "plugin.invoke_tool",
                    "activation_type": str(getattr(instance, "activation_type", "always")),
                    "action_parameters": parameters,
                    "parallel_action": bool(getattr(instance, "parallel_action", False)),
                    "handler_name": f"_amind_dispatch__{name}",
                    "legacy": True,
                },
            }
        logger.warning(f"[A_Mind] 跳过未知组件类型: {ctype} ({name})")
        return None

    async def _dispatch_command(self, **kwargs):
        component_name = _infer_component_name(kwargs, self._component_map, "COMMAND")
        instance = self._component_instances[component_name]
        message = _build_legacy_message(kwargs)
        instance.message = message
        instance.plugin_config = self.get_plugin_config_data()
        instance.container = self._legacy.container
        instance.plugin_dir = self.plugin_dir
        instance._plugin = self._legacy
        instance._stream_id = str(kwargs.get("stream_id", "") or getattr(message, "session_id", "") or "")
        groups = kwargs.get("matched_groups") if isinstance(kwargs.get("matched_groups"), dict) else {}
        if not groups:
            pattern = str(self._component_map.get(component_name, {}).get("metadata", {}).get("command_pattern", "") or "")
            text = str(getattr(message, "plain_text", "") or getattr(message, "processed_plain_text", "") or "")
            if pattern and text:
                match = re.match(pattern, text)
                if match:
                    groups = match.groupdict()
        if hasattr(instance, "set_matched_groups"):
            instance.set_matched_groups(groups)
        else:
            instance.matched_groups = groups
        with self._legacy_context():
            return await instance.execute()

    async def _dispatch_event(self, **kwargs):
        component_name = _infer_component_name(kwargs, self._component_map, "EVENT_HANDLER")
        instance = self._component_instances[component_name]
        if hasattr(instance, "set_plugin_config"):
            instance.set_plugin_config(self.get_plugin_config_data())
        if hasattr(instance, "set_plugin_name"):
            instance.set_plugin_name("a_mind")
        message = _dict_to_namespace(kwargs.get("message")) if isinstance(kwargs.get("message"), dict) else kwargs.get("message")
        if message is not None and not getattr(message, "stream_id", None):
            setattr(message, "stream_id", str(kwargs.get("stream_id", "") or getattr(message, "session_id", "") or ""))
        with self._legacy_context():
            return await instance.execute(message)

    async def _dispatch_action(self, **kwargs):
        component_name = _infer_component_name(kwargs, self._component_map, "TOOL")
        instance = self._component_instances[component_name]
        instance.plugin_config = self.get_plugin_config_data()
        instance.container = self._legacy.container
        instance.plugin_dir = self.plugin_dir
        instance._plugin = self._legacy
        instance.action_data = _extract_tool_action_data(kwargs)
        instance.action_reasoning = str(kwargs.get("reasoning", "") or kwargs.get("action_reasoning", "") or "")
        instance._stream_id = str(kwargs.get("stream_id", "") or kwargs.get("chat_id", "") or "")
        instance.chat_id = instance._stream_id
        for attr in ("thinking_id", "cycle_timers", "chat_stream", "action_message", "message"):
            if attr in kwargs:
                setattr(instance, attr, kwargs[attr])
        with self._legacy_context():
            return await instance.execute()

    @contextlib.contextmanager
    def _legacy_context(self):
        plugin_id = self.ctx.plugin_id if self._ctx else ""
        token = _context_holder.activate_plugin(plugin_id)
        try:
            yield
        finally:
            _context_holder.deactivate_plugin(token)


def _get_nested_config(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    current: Any = config
    for part in str(key or "").split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _merge_config(default_config: Dict[str, Any], current_config: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(default_config)
    for key, value in dict(current_config or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _schema_to_default_config(schema: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in dict(schema or {}).items():
        if hasattr(value, "default"):
            result[key] = getattr(value, "default")
        elif isinstance(value, dict):
            result[key] = _schema_to_default_config(value)
    return result


def _dict_to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{str(k): _dict_to_namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_dict_to_namespace(item) for item in value]
    return value


def _build_legacy_message(kwargs: Dict[str, Any]) -> Any:
    message = _dict_to_namespace(kwargs.get("message")) if isinstance(kwargs.get("message"), dict) else kwargs.get("message")
    if message is None:
        text = str(kwargs.get("text", "") or "")
        stream_id = str(kwargs.get("stream_id", "") or "")
        user_id = str(kwargs.get("user_id", "") or "")
        group_id = str(kwargs.get("group_id", "") or "")
        user_info = SimpleNamespace(user_id=user_id, user_nickname="")
        group_info = SimpleNamespace(group_id=group_id, group_name="")
        message_info = SimpleNamespace(user_info=user_info, group_info=group_info, message_id="")
        message = SimpleNamespace(
            plain_text=text,
            processed_plain_text=text,
            stream_id=stream_id,
            session_id=stream_id,
            user_id=user_id,
            sender=user_info,
            message_info=message_info,
            chat_stream=SimpleNamespace(stream_id=stream_id, session_id=stream_id),
        )
    else:
        if not hasattr(message, "plain_text"):
            setattr(message, "plain_text", getattr(message, "processed_plain_text", ""))
        if not hasattr(message, "processed_plain_text"):
            setattr(message, "processed_plain_text", getattr(message, "plain_text", ""))
        if not hasattr(message, "stream_id"):
            setattr(message, "stream_id", getattr(message, "session_id", str(kwargs.get("stream_id", "") or "")))
        if not hasattr(message, "session_id"):
            setattr(message, "session_id", getattr(message, "stream_id", str(kwargs.get("stream_id", "") or "")))
        user_info = getattr(getattr(message, "message_info", None), "user_info", None)
        if user_info is not None:
            if not hasattr(message, "user_id"):
                setattr(message, "user_id", str(getattr(user_info, "user_id", "") or ""))
            if not hasattr(message, "sender"):
                setattr(message, "sender", user_info)
    return message


def _infer_component_name(kwargs: Dict[str, Any], component_map: Dict[str, Dict[str, Any]], component_type: str) -> str:
    explicit = str(kwargs.get("component_name", "") or kwargs.get("name", "") or "").strip()
    if explicit and explicit in component_map:
        return explicit
    candidates = [name for name, comp in component_map.items() if comp.get("type") == component_type]
    if len(candidates) == 1:
        return candidates[0]
    text = str(kwargs.get("text", "") or "")
    if component_type == "COMMAND" and text:
        for name in candidates:
            pattern = str(component_map[name].get("metadata", {}).get("command_pattern", "") or "")
            if pattern and re.match(pattern, text):
                return name
    raise KeyError(f"无法确定 {component_type} 组件: {explicit or '<empty>'}")


def _legacy_action_parameters_to_tool_schema(parameters: Dict[str, Any]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    for name, description in dict(parameters or {}).items():
        parameter_name = str(name or "").strip()
        if not parameter_name:
            continue
        properties[parameter_name] = {
            "type": "string",
            "description": str(description or "").strip() or "兼容旧 Action 参数",
        }
    return {"type": "object", "properties": properties} if properties else {}


def _legacy_action_tool_description(instance: Any, parameters_schema: Dict[str, Any]) -> str:
    parts = []
    description = str(getattr(instance, "action_description", "") or "").strip()
    if description:
        parts.append(description)
    properties = parameters_schema.get("properties") if isinstance(parameters_schema, dict) else {}
    if isinstance(properties, dict) and properties:
        lines = ["参数说明："]
        for name, schema in properties.items():
            schema = schema if isinstance(schema, dict) else {}
            lines.append(f"- {name}: {schema.get('description', '兼容旧 Action 参数')}")
        parts.append("\n".join(lines))
    requirements = [
        str(item).strip()
        for item in (getattr(instance, "action_require", []) or [])
        if str(item).strip()
    ]
    if requirements:
        parts.append("使用建议：\n" + "\n".join(f"- {item}" for item in requirements))
    associated_types = [
        str(item).strip()
        for item in (getattr(instance, "associated_types", []) or [])
        if str(item).strip()
    ]
    if associated_types:
        parts.append(f"适用消息类型：{', '.join(associated_types)}")
    return "\n\n".join(parts)


def _extract_tool_action_data(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(kwargs.get("action_data"), dict):
        return dict(kwargs["action_data"])
    ignored_keys = {
        "component_name",
        "reasoning",
        "action_reasoning",
        "stream_id",
        "chat_id",
        "thinking_id",
        "cycle_timers",
        "chat_stream",
        "action_message",
        "message",
    }
    return {key: value for key, value in kwargs.items() if key not in ignored_keys}


def create_plugin() -> AMindSDKPlugin:
    return AMindSDKPlugin()


def _install_legacy_llm_patch() -> None:
    try:
        from maibot_sdk.compat.apis import llm_api as compat_llm_api
    except Exception:
        return

    def _amind_get_available_models() -> Dict[str, Any]:
        return {
            "tool_use": {"name": "tool_use"},
            "replyer": {"name": "replyer"},
            "planner": {"name": "planner"},
            "utils": {"name": "utils"},
        }

    async def _amind_generate_with_model(
        prompt: str,
        model_config: Any = None,
        request_type: str = "plugin.generate",
        temperature: float = None,
        max_tokens: int = None,
        **kwargs: Any,
    ) -> Tuple[bool, str, str, str]:
        del request_type
        ctx = _context_holder.get_context()
        if ctx is None:
            return False, "", "", ""
        model_name = _extract_model_name(model_config)
        try:
            result = await ctx.llm.generate(
                prompt=prompt,
                model=model_name,
                temperature=temperature if temperature is not None else 0.7,
                max_tokens=max_tokens if max_tokens is not None else 2000,
                **kwargs,
            )
        except Exception as exc:
            logger.error(f"[A_Mind] LLM兼容调用失败: {exc}")
            return False, str(exc), "", model_name
        if isinstance(result, dict):
            ok = bool(result.get("success", True))
            content = str(result.get("response", result.get("content", "")) or "")
            reasoning = str(result.get("reasoning", "") or "")
            used_model = str(result.get("model", result.get("model_name", model_name)) or model_name)
            return ok, content, reasoning, used_model
        return True, str(result), "", model_name

    modules_to_patch = []
    for module_name in ("maibot_sdk.compat.apis.llm_api", "src.plugin_system.apis.llm_api"):
        module = sys.modules.get(module_name)
        if module is None:
            with contextlib.suppress(Exception):
                module = importlib.import_module(module_name)
        if module is not None and module not in modules_to_patch:
            modules_to_patch.append(module)
    if compat_llm_api not in modules_to_patch:
        modules_to_patch.append(compat_llm_api)

    for llm_module in modules_to_patch:
        llm_module.get_available_models = _amind_get_available_models
        llm_module.generate_with_model = _amind_generate_with_model
        llm_module._amind_patched = True

    with contextlib.suppress(Exception):
        apis_pkg = importlib.import_module("maibot_sdk.compat.apis")
        apis_pkg.llm_api = modules_to_patch[0]
    with contextlib.suppress(Exception):
        apis_pkg = importlib.import_module("src.plugin_system.apis")
        apis_pkg.llm_api = modules_to_patch[-1]

    plugin_root = Path(__file__).parent.resolve()
    for module in list(sys.modules.values()):
        module_name = str(getattr(module, "__name__", "") or "")
        module_file = str(getattr(module, "__file__", "") or "")
        try:
            is_plugin_module = bool(module_file) and Path(module_file).resolve().is_relative_to(plugin_root)
        except Exception:
            is_plugin_module = False
        if (
            not is_plugin_module
            and ".A_Mind." not in module_name
            and not module_name.endswith("A_Mind")
            and not module_name.startswith("_maibot_plugin_")
        ):
            continue
        if hasattr(module, "get_available_models"):
            with contextlib.suppress(Exception):
                setattr(module, "get_available_models", _amind_get_available_models)
        if getattr(module, "llm_api", None) is compat_llm_api:
            with contextlib.suppress(Exception):
                setattr(module, "llm_api", compat_llm_api)


def _extract_model_name(model_config: Any) -> str:
    if isinstance(model_config, str):
        return model_config
    if isinstance(model_config, dict):
        for key in ("name", "model_name", "task_name"):
            value = str(model_config.get(key, "") or "").strip()
            if value:
                return value
    for key in ("name", "model_name", "task_name"):
        value = str(getattr(model_config, key, "") or "").strip()
        if value:
            return value
    return ""


_install_legacy_llm_patch()


# get_global_db_manager现在在utils.py中定义
