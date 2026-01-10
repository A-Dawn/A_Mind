"""
话题数据访问层

提供话题相关的数据库操作
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.topic import Topic, TopicStreamState


class TopicRepository:
    """话题数据访问对象"""

    def __init__(self, db_manager):
        """初始化话题仓库

        Args:
            db_manager: 数据库管理器实例
        """
        self.db_manager = db_manager

    def create_topic(self, topic) -> Optional[int]:
        """创建话题"""
        return self.db_manager.create_topic(topic)

    def get_topic(self, topic_id: int):
        """获取话题"""
        return self.db_manager.get_topic(topic_id)

    def list_topics(self, status_filter: Optional[str] = None) -> List:
        """获取话题列表"""
        return self.db_manager.list_topics(status_filter)

    def update_topic(self, topic_id: int, updates: Dict[str, Any]) -> bool:
        """更新话题"""
        return self.db_manager.update_topic(topic_id, updates)

    def delete_topic(self, topic_id: int) -> bool:
        """删除话题"""
        return self.db_manager.delete_topic(topic_id)

    def get_topic_stream_state(self, topic_id: int, stream_id: str):
        """获取话题在特定聊天流的状态"""
        return self.db_manager.get_topic_stream_state(topic_id, stream_id)

    def update_topic_stream_state(self, topic_id: int, stream_id: str, updates: Dict[str, Any]) -> bool:
        """更新话题在特定聊天流的状态"""
        return self.db_manager.update_topic_stream_state(topic_id, stream_id, updates)

    def list_topics_for_stream(self, stream_id: str, status_filter: Optional[str] = None) -> List:
        """获取特定聊天流可见的话题列表"""
        return self.db_manager.list_topics_for_stream(stream_id, status_filter)

    def get_recent_replies(self, topic_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取话题的最近回复"""
        return self.db_manager.get_recent_replies(topic_id, limit)
