"""
监控和指标相关数据模型

包含EngagementMetrics、MonitoringResult等数据模型
"""

import time
from typing import List
from dataclasses import dataclass


@dataclass
class EngagementMetrics:
    """参与度指标"""

    reply_count: int = 0
    unique_users: int = 0
    avg_response_time: float = 0.0
    sentiment_score: float = 0.5
    sustained_attention: float = 0.0  # 持续关注度
    conversation_depth: float = 0.0  # 对话深度
    measured_at: float = 0

    def __post_init__(self):
        if self.measured_at == 0:
            self.measured_at = time.time()


@dataclass
class MonitoringResult:
    """监测结果"""

    topic_id: int = 0
    success_score: float = 0.0  # 自发起成功度
    engagement_trend: str = "stable"  # increasing, decreasing, stable
    recommendations: List[str] = None
    next_action: str = "continue"  # continue, followup, terminate, retry
    monitored_at: float = 0

    def __post_init__(self):
        if self.recommendations is None:
            self.recommendations = []
        if self.monitored_at == 0:
            self.monitored_at = time.time()

