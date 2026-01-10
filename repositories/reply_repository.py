"""
回复数据访问层

提供回复记录相关的数据库操作
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.topic import TopicReply


class ReplyRepository:
    """回复数据访问对象"""

    def __init__(self, db_manager):
        """初始化回复仓库

        Args:
            db_manager: 数据库管理器实例
        """
        self.db_manager = db_manager

    def add_reply_record(self, reply) -> Optional[int]:
        """添加回复记录"""
        return self.db_manager.add_reply_record(reply)

    def get_recent_replies(self, topic_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取话题的最近回复"""
        return self.db_manager.get_recent_replies(topic_id, limit)
