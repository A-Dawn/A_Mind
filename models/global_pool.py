"""
总控池数据模型
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PoolEvent:
    """总控池事件记录"""

    id: Optional[int] = None
    stream_id: str = ""
    message_id: str = ""
    user_id_hash: str = ""
    role: str = "user"
    summary_text: str = ""
    raw_text: str = ""
    features: Dict[str, Any] = None
    created_at: float = 0
    summary_expire_at: float = 0
    raw_expire_at: float = 0

    def __post_init__(self):
        if self.features is None:
            self.features = {}
        now = time.time()
        if self.created_at == 0:
            self.created_at = now
        if self.summary_expire_at == 0:
            self.summary_expire_at = now + 72 * 3600
        if self.raw_expire_at == 0:
            self.raw_expire_at = now + 24 * 3600


@dataclass
class PoolDecision:
    """总控池决策记录"""

    id: Optional[int] = None
    stream_id: str = ""
    policy_profile: str = "conservative"
    decision: Dict[str, Any] = None
    selected_topic_title: str = ""
    score: float = 0.0
    sent: bool = False
    reason: str = ""
    created_at: float = 0

    def __post_init__(self):
        if self.decision is None:
            self.decision = {}
        if self.created_at == 0:
            self.created_at = time.time()


@dataclass
class PoolCandidate:
    """总控池候选话题"""

    stream_id: str = ""
    keyword: str = ""
    title: str = ""
    description: str = ""
    opener: str = ""
    interest_score: float = 0.0
    novelty_score: float = 0.0
    cross_stream_score: float = 0.0
    repeat_penalty: float = 0.0
    final_score: float = 0.0
    source_samples: List[str] = None

    def __post_init__(self):
        if self.source_samples is None:
            self.source_samples = []
