"""
数据模型包

包含A_Mind插件的所有数据模型定义
"""

from .topic import Topic, TopicStreamState, TopicReply
from .search import SearchResult, KnowledgeItem
from .brainstorm import BrainstormTopic, DecisionResult
from .auto_send import AutoSendRequest, SendResult
from .metrics import EngagementMetrics, MonitoringResult
from .global_pool import PoolEvent, PoolDecision, PoolCandidate

__all__ = [
    # 话题相关
    'Topic', 'TopicStreamState', 'TopicReply',
    # 搜索相关
    'SearchResult', 'KnowledgeItem',
    # 头脑风暴相关
    'BrainstormTopic', 'DecisionResult',
    # 自动发送相关
    'AutoSendRequest', 'SendResult',
    # 监控指标相关
    'EngagementMetrics', 'MonitoringResult',
    # 总控池相关
    'PoolEvent', 'PoolDecision', 'PoolCandidate',
]
