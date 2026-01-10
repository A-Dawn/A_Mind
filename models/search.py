"""
搜索和知识库相关数据模型

包含SearchResult、KnowledgeItem等数据模型
"""

import time
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class SearchResult:
    """搜索结果数据模型"""

    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""
    relevance_score: float = 0.0
    timestamp: float = 0

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class KnowledgeItem:
    """知识库条目数据模型"""

    id: Optional[int] = None
    title: str = ""
    content: str = ""
    category: str = ""
    tags: List[str] = None
    source: str = ""
    relevance_score: float = 0.0
    created_at: float = 0
    updated_at: float = 0

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at == 0:
            self.created_at = time.time()
        if self.updated_at == 0:
            self.updated_at = time.time()

