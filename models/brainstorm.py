"""
头脑风暴相关数据模型

包含BrainstormTopic、DecisionResult等数据模型
"""

from typing import Optional, List, Dict
from dataclasses import dataclass


@dataclass
class BrainstormTopic:
    """头脑风暴生成的话题"""

    title: str = ""
    description: str = ""
    category: str = ""
    relevance_score: float = 0.0
    novelty_score: float = 0.0
    engagement_potential: float = 0.0
    reasoning: str = ""
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class DecisionResult:
    """决策选择结果"""

    selected_topic: Optional[BrainstormTopic] = None
    confidence_score: float = 0.0
    reasoning: str = ""
    alternatives: List[BrainstormTopic] = None
    selection_criteria: Dict[str, float] = None

    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []
        if self.selection_criteria is None:
            self.selection_criteria = {}

