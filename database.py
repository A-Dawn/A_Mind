"""
A_Mind插件专用数据库管理模块
"""

import sqlite3
import os
import threading
from typing import Optional
from pathlib import Path

# Logger import with fallback
try:
    from .core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

logger = get_logger(__name__)

# 数据库文件路径
PLUGIN_DIR = Path(__file__).parent
DATA_DIR = PLUGIN_DIR / "data"
DB_PATH = DATA_DIR / "amind.db"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

# 全局数据库连接（简化版本）
_connection = None

# 数据库管理器单例
_db_manager = None

class DatabaseManager:
    """数据库管理器单例"""

    def __init__(self):
        pass

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（每次都返回新连接）"""
        conn = sqlite3.connect(
            str(DB_PATH),
            check_same_thread=True,  # 单线程访问
            timeout=30.0  # 连接超时时间
        )

        # 设置行工厂，返回字典而不是元组
        conn.row_factory = sqlite3.Row

        # 启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")

        # 设置WAL模式以提高并发性能
        conn.execute("PRAGMA journal_mode = WAL")

        # 设置同步模式为NORMAL（平衡性能和安全性）
        conn.execute("PRAGMA synchronous = NORMAL")

        return conn

    def close_connection(self):
        """关闭数据库连接（不再需要，因为每次都返回新连接）"""
        pass

def get_db_manager() -> DatabaseManager:
    """获取数据库管理器单例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager

def get_db_connection() -> sqlite3.Connection:
    """
    获取数据库连接

    Returns:
        sqlite3.Connection: 数据库连接对象
    """
    return get_db_manager().get_connection()

def close_db_connection():
    """关闭数据库连接"""
    get_db_manager().close_connection()

def init_database():
    """初始化数据库表结构"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 创建话题表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS amind_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                creator_id TEXT NOT NULL,
                creator_name TEXT,
                status TEXT DEFAULT 'active',
                priority INTEGER DEFAULT 1,
                visibility TEXT DEFAULT 'public',
                allowed_users TEXT,
                created_at REAL DEFAULT 0,
                updated_at REAL DEFAULT 0,
                last_activity REAL DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                engagement_score REAL DEFAULT 0.0,
                config TEXT,
                check_count INTEGER DEFAULT 0,
                last_check_at REAL DEFAULT 0,
                auto_initiate_count INTEGER DEFAULT 0,
                last_auto_initiate_at REAL DEFAULT 0
            )
        ''')

        # 创建回复记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS amind_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                stream_id TEXT,
                message_id TEXT,
                user_id TEXT,
                user_name TEXT,
                message_content TEXT,
                reply_content TEXT,
                match_score REAL DEFAULT 0.0,
                quality_score REAL DEFAULT 0.0,
                created_at REAL DEFAULT 0,
                FOREIGN KEY (topic_id) REFERENCES amind_topics(id) ON DELETE CASCADE
            )
        ''')

        # 创建状态检查记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS amind_state_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                check_type TEXT,
                engagement_score REAL,
                sentiment_score REAL,
                progress_score REAL,
                recommendation TEXT,
                action_taken TEXT,
                created_at REAL DEFAULT 0,
                FOREIGN KEY (topic_id) REFERENCES amind_topics(id) ON DELETE CASCADE
            )
        ''')

        # 创建权限配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                permission_level TEXT DEFAULT 'user',
                granted_by TEXT,
                granted_at REAL DEFAULT 0
            )
        ''')

        # 创建知识库表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS amind_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                tags TEXT,  -- JSON格式的标签列表
                source TEXT,
                relevance_score REAL DEFAULT 0.0,
                created_at REAL DEFAULT 0,
                updated_at REAL DEFAULT 0
            )
        ''')

        # 创建索引以提高查询性能
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_topics_status ON amind_topics(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_topics_creator ON amind_topics(creator_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_topics_created ON amind_topics(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_replies_topic ON amind_replies(topic_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_replies_created ON amind_replies(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_knowledge_title ON amind_knowledge(title)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_amind_knowledge_category ON amind_knowledge(category)')

        conn.commit()
        logger.info(f"数据库初始化完成: {DB_PATH}")

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()

def get_database_stats() -> dict:
    """获取数据库统计信息"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        stats = {}

        # 话题统计
        cursor.execute("SELECT COUNT(*) as count FROM amind_topics")
        stats['total_topics'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM amind_topics WHERE status = 'active'")
        stats['active_topics'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM amind_topics WHERE status = 'completed'")
        stats['completed_topics'] = cursor.fetchone()['count']

        # 回复统计
        cursor.execute("SELECT COUNT(*) as count FROM amind_replies")
        stats['total_replies'] = cursor.fetchone()['count']

        # 知识库统计
        cursor.execute("SELECT COUNT(*) as count FROM amind_knowledge")
        stats['total_knowledge_items'] = cursor.fetchone()['count']

        # 状态检查统计
        cursor.execute("SELECT COUNT(*) as count FROM amind_state_checks")
        stats['total_state_checks'] = cursor.fetchone()['count']

        # 数据库文件大小
        if DB_PATH.exists():
            stats['db_size_mb'] = DB_PATH.stat().st_size / (1024 * 1024)
        else:
            stats['db_size_mb'] = 0

        return stats

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return {}
    finally:
        cursor.close()

# 清理函数
def cleanup_connections():
    """清理所有数据库连接（在程序退出时调用）"""
    close_db_connection()
