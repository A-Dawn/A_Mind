"""
数据库管理器

提供数据库连接管理和基础的数据访问功能
"""

import sqlite3
import time
from typing import Optional, Dict, List, Any, TYPE_CHECKING

# 运行时需要导入数据模型
from ..models.topic import Topic, TopicStreamState, TopicReply
from pathlib import Path

try:
    from ..database import get_db_connection, init_database
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from database import get_db_connection, init_database


class DatabaseManager:
    """数据库管理器 - 提供基础的数据访问功能"""

    def __init__(self, db_manager=None):
        """初始化数据库管理器

        Args:
            db_manager: 底层数据库管理器（向后兼容）
        """
        self.db_manager = db_manager
        # 确保数据库表存在
        init_database()
        # 初始化时执行数据库架构迁移
        self.migrate_database_schema()

    def create_topic(self, topic) -> Optional[int]:
        """创建话题"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO amind_topics
                (title, description, creator_id, creator_name, status, priority,
                 visibility, allowed_users, stream_ids, created_at, updated_at, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    topic.title,
                    topic.description,
                    topic.creator_id,
                    topic.creator_name,
                    topic.status,
                    topic.priority,
                    topic.visibility,
                    str(topic.allowed_users) if topic.allowed_users else "[]",
                    str(topic.stream_ids) if topic.stream_ids else "[]",
                    topic.created_at,
                    topic.updated_at,
                    str(topic.config) if topic.config else "{}",
                ),
            )

            topic_id = cursor.lastrowid
            conn.commit()

            # 为每个绑定的聊天流创建初始状态
            if topic.stream_ids:
                for stream_id in topic.stream_ids:
                    self._create_topic_stream_state(topic_id, stream_id)

            return topic_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _create_topic_stream_state(self, topic_id: int, stream_id: str) -> bool:
        """为话题创建聊天流状态记录"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO amind_topic_stream_states
                (topic_id, stream_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (topic_id, stream_id, "active", time.time(), time.time())
            )
            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_topic(self, topic_id: int):
        """获取话题"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM amind_topics WHERE id = ?", (topic_id,))
            row = cursor.fetchone()

            if row:
                return Topic(
                    id=row[0],
                    title=row[1],
                    description=row[2],
                    creator_id=row[3],
                    creator_name=row[4],
                    status=row[5],
                    priority=row[6],
                    visibility=row[7],
                    allowed_users=eval(row[8]) if row[8] else [],
                    created_at=row[9],
                    updated_at=row[10],
                    last_activity=row[11],
                    reply_count=row[12],
                    engagement_score=row[13],
                    config=eval(row[14]) if row[14] else {},
                    check_count=row[15],
                    last_check_at=row[16],
                    auto_initiate_count=row[17],
                    last_auto_initiate_at=row[18],
                    stream_ids=eval(row[19]) if len(row) > 19 and row[19] else [],
                )

        except Exception as e:
            raise e
        finally:
            conn.close()

        return None

    def list_topics(self, status_filter: Optional[str] = None) -> List:
        """获取话题列表"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if status_filter:
                cursor.execute(
                    "SELECT * FROM amind_topics WHERE status = ? ORDER BY created_at DESC", (status_filter,)
                )
            else:
                cursor.execute("SELECT * FROM amind_topics ORDER BY created_at DESC")

            topics = []
            for row in cursor.fetchall():
                topics.append(
                    Topic(
                        id=row[0],
                        title=row[1],
                        description=row[2],
                        creator_id=row[3],
                        creator_name=row[4],
                        status=row[5],
                        priority=row[6],
                        visibility=row[7],
                        allowed_users=eval(row[8]) if row[8] else [],
                        created_at=row[9],
                        updated_at=row[10],
                        last_activity=row[11],
                        reply_count=row[12],
                        engagement_score=row[13],
                        config=eval(row[14]) if row[14] else {},
                        check_count=row[15],
                        last_check_at=row[16],
                        auto_initiate_count=row[17],
                        last_auto_initiate_at=row[18],
                        stream_ids=eval(row[19]) if len(row) > 19 and row[19] else [],
                    )
                )

            return topics

        except Exception as e:
            raise e
        finally:
            conn.close()

    def update_topic(self, topic_id: int, updates: Dict[str, Any]) -> bool:
        """更新话题"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 构建更新语句
            set_parts = []
            values = []
            for key, value in updates.items():
                if key in ["allowed_users", "stream_ids", "config"] and isinstance(value, (list, dict)):
                    set_parts.append(f"{key} = ?")
                    values.append(str(value))
                else:
                    set_parts.append(f"{key} = ?")
                    values.append(value)

            # 添加更新时间
            set_parts.append("updated_at = ?")
            values.append(time.time())

            set_clause = ", ".join(set_parts)
            values.append(topic_id)

            cursor.execute(f"UPDATE amind_topics SET {set_clause} WHERE id = ?", values)
            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def delete_topic(self, topic_id: int) -> bool:
        """删除话题"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM amind_topics WHERE id = ?", (topic_id,))
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def add_reply_record(self, reply) -> Optional[int]:
        """添加回复记录"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO amind_replies
                (topic_id, stream_id, message_id, user_id, user_name,
                 message_content, reply_content, match_score, quality_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    reply.topic_id,
                    reply.stream_id,
                    reply.message_id,
                    reply.user_id,
                    reply.user_name,
                    reply.message_content,
                    reply.reply_content,
                    reply.match_score,
                    reply.quality_score,
                    reply.created_at,
                ),
            )

            reply_id = cursor.lastrowid
            conn.commit()
            return reply_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def add_state_check_record(self, check_record: dict) -> Optional[int]:
        """添加状态检查记录"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO amind_state_checks
                (topic_id, check_type, engagement_score, sentiment_score,
                 progress_score, recommendation, action_taken, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    check_record["topic_id"],
                    check_record["check_type"],
                    check_record["engagement_score"],
                    check_record["sentiment_score"],
                    check_record["progress_score"],
                    check_record["recommendation"],
                    check_record["action_taken"],
                    check_record["created_at"],
                ),
            )

            check_id = cursor.lastrowid
            conn.commit()
            return check_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_topic_stream_state(self, topic_id: int, stream_id: str):
        """获取话题在特定聊天流的状态"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM amind_topic_stream_states WHERE topic_id = ? AND stream_id = ?",
                (topic_id, stream_id)
            )
            row = cursor.fetchone()

            if row:
                return TopicStreamState(
                    id=row[0],
                    topic_id=row[1],
                    stream_id=row[2],
                    status=row[3],
                    local_config=eval(row[4]) if row[4] else {},
                    created_at=row[5],
                    updated_at=row[6],
                    last_activity=row[7],
                    reply_count=row[8],
                    engagement_score=row[9],
                    check_count=row[10],
                    last_check_at=row[11],
                    auto_initiate_count=row[12],
                    last_auto_initiate_at=row[13],
                )

        except Exception as e:
            raise e
        finally:
            conn.close()

        return None

    def update_topic_stream_state(self, topic_id: int, stream_id: str, updates: Dict[str, Any]) -> bool:
        """更新话题在特定聊天流的状态"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 构建更新语句
            set_parts = []
            values = []
            for key, value in updates.items():
                if key == "local_config" and isinstance(value, dict):
                    set_parts.append(f"{key} = ?")
                    values.append(str(value))
                else:
                    set_parts.append(f"{key} = ?")
                    values.append(value)

            # 添加更新时间
            set_parts.append("updated_at = ?")
            values.append(time.time())

            set_clause = ", ".join(set_parts)
            values.extend([topic_id, stream_id])

            cursor.execute(f"UPDATE amind_topic_stream_states SET {set_clause} WHERE topic_id = ? AND stream_id = ?", values)
            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def list_topics_for_stream(self, stream_id: str, status_filter: Optional[str] = None) -> List:
        """获取特定聊天流可见的话题列表"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 查询绑定到指定聊天流的活跃话题
            if status_filter:
                cursor.execute(
                    """
                    SELECT t.* FROM amind_topics t
                    INNER JOIN amind_topic_stream_states s ON t.id = s.topic_id
                    WHERE s.stream_id = ? AND s.status = ? AND t.status = ?
                    ORDER BY t.created_at DESC
                    """,
                    (stream_id, "active", status_filter)
                )
            else:
                cursor.execute(
                    """
                    SELECT t.* FROM amind_topics t
                    INNER JOIN amind_topic_stream_states s ON t.id = s.topic_id
                    WHERE s.stream_id = ? AND s.status = ?
                    ORDER BY t.created_at DESC
                    """,
                    (stream_id, "active")
                )

            topics = []
            for row in cursor.fetchall():
                topics.append(
                    Topic(
                        id=row[0],
                        title=row[1],
                        description=row[2],
                        creator_id=row[3],
                        creator_name=row[4],
                        status=row[5],
                        priority=row[6],
                        visibility=row[7],
                        allowed_users=eval(row[8]) if row[8] else [],
                        created_at=row[9],
                        updated_at=row[10],
                        last_activity=row[11],
                        reply_count=row[12],
                        engagement_score=row[13],
                        config=eval(row[14]) if row[14] else {},
                        check_count=row[15],
                        last_check_at=row[16],
                        auto_initiate_count=row[17],
                        last_auto_initiate_at=row[18],
                        stream_ids=eval(row[19]) if len(row) > 19 and row[19] else [],
                    )
                )

            return topics

        except Exception as e:
            raise e
        finally:
            conn.close()

    def get_recent_replies(self, topic_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """获取话题的最近回复"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM amind_replies WHERE topic_id = ? ORDER BY created_at DESC LIMIT ?",
                (topic_id, limit)
            )

            replies = []
            for row in cursor.fetchall():
                replies.append({
                    'id': row[0],
                    'topic_id': row[1],
                    'stream_id': row[2],
                    'message_id': row[3],
                    'user_id': row[4],
                    'user_name': row[5],
                    'message_content': row[6],
                    'reply_content': row[7],
                    'match_score': row[8],
                    'quality_score': row[9],
                    'created_at': row[10],
                })

            return replies

        except Exception as e:
            raise e
        finally:
            conn.close()

    def migrate_database_schema(self) -> bool:
        """迁移数据库架构以支持完全隔离模式"""
        # 首先确保基础表存在
        init_database()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 检查并添加stream_ids字段到amind_topics表
            cursor.execute("PRAGMA table_info(amind_topics)")
            columns = [row[1] for row in cursor.fetchall()]

            if "stream_ids" not in columns:
                cursor.execute("ALTER TABLE amind_topics ADD COLUMN stream_ids TEXT DEFAULT '[]'")
                conn.commit()

            # 检查并创建amind_topic_stream_states表
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='amind_topic_stream_states'
            """)
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE amind_topic_stream_states (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic_id INTEGER NOT NULL,
                        stream_id TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        local_config TEXT DEFAULT '{}',
                        created_at REAL DEFAULT 0,
                        updated_at REAL DEFAULT 0,
                        last_activity REAL DEFAULT 0,
                        reply_count INTEGER DEFAULT 0,
                        engagement_score REAL DEFAULT 0.0,
                        check_count INTEGER DEFAULT 0,
                        last_check_at REAL DEFAULT 0,
                        auto_initiate_count INTEGER DEFAULT 0,
                        last_auto_initiate_at REAL DEFAULT 0,
                        FOREIGN KEY (topic_id) REFERENCES amind_topics (id) ON DELETE CASCADE,
                        UNIQUE(topic_id, stream_id)
                    )
                """)
                conn.commit()

            # 检查并添加stream_id字段到amind_replies表
            cursor.execute("PRAGMA table_info(amind_replies)")
            reply_columns = [row[1] for row in cursor.fetchall()]

            if "stream_id" not in reply_columns:
                cursor.execute("ALTER TABLE amind_replies ADD COLUMN stream_id TEXT")
                conn.commit()

            return True

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_meta(self, key: str, default: str = None) -> Optional[str]:
        """获取元数据"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT value FROM amind_meta WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
        except Exception as e:
            conn.close() # Ensure connection is closed on error
            # 记录错误但不要抛出，以免影响主流程
            return default
        finally:
            conn.close()

    def set_meta(self, key: str, value: str) -> bool:
        """设置元数据"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO amind_meta (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
                (key, str(value), time.time()),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            return False
        finally:
            conn.close()
