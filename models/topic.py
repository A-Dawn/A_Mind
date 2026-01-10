"""
话题相关数据模型

包含Topic、TopicStreamState、TopicReply等核心数据模型
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class Topic:
    """话题数据模型"""

    id: Optional[int] = None
    title: str = ""
    description: str = ""
    creator_id: str = ""
    creator_name: str = ""
    status: str = "active"
    priority: int = 1
    visibility: str = "public"
    allowed_users: List[str] = None
    stream_ids: List[str] = None  # 绑定的聊天流ID列表，完全隔离模式
    created_at: float = 0
    updated_at: float = 0
    last_activity: float = 0
    reply_count: int = 0
    engagement_score: float = 0.0
    config: Dict[str, Any] = None
    check_count: int = 0
    last_check_at: float = 0
    auto_initiate_count: int = 0
    last_auto_initiate_at: float = 0

    def __post_init__(self):
        if self.allowed_users is None:
            self.allowed_users = []
        if self.stream_ids is None:
            self.stream_ids = []
        if self.config is None:
            self.config = {}
        if self.created_at == 0:
            self.created_at = time.time()
        if self.updated_at == 0:
            self.updated_at = time.time()


@dataclass
class TopicStreamState:
    """话题聊天流状态数据模型 - 完全隔离模式"""

    id: Optional[int] = None
    topic_id: int = 0
    stream_id: str = ""
    status: str = "active"  # active/paused/completed/terminated
    local_config: Dict[str, Any] = None  # 聊天流特定的配置
    created_at: float = 0
    updated_at: float = 0
    last_activity: float = 0
    reply_count: int = 0
    engagement_score: float = 0.0
    check_count: int = 0
    last_check_at: float = 0
    auto_initiate_count: int = 0
    last_auto_initiate_at: float = 0

    def __post_init__(self):
        if self.local_config is None:
            self.local_config = {}
        if self.created_at == 0:
            self.created_at = time.time()
        if self.updated_at == 0:
            self.updated_at = time.time()


@dataclass
class TopicReply:
    """回复记录数据模型"""

    id: Optional[int] = None
    topic_id: int = 0
    stream_id: str = ""  # 添加聊天流ID，便于统计
    message_id: str = ""
    user_id: str = ""
    user_name: str = ""
    message_content: str = ""
    reply_content: str = ""
    match_score: float = 0.0
    quality_score: float = 0.0
    created_at: float = 0

    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = time.time()

