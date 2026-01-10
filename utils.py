"""
A_mind工具函数

包含全局数据库管理器等工具函数
"""

# 向后兼容：保持全局数据库管理器实例
_db_manager_instance = None


def get_global_db_manager():
    """获取全局数据库管理器实例（向后兼容）"""
    global _db_manager_instance
    if _db_manager_instance is None:
        # 创建插件自己的业务逻辑管理器
        try:
            from .repositories.database_manager import DatabaseManager
        except ImportError:
            from plugins.A_Mind.repositories.database_manager import DatabaseManager
        _db_manager_instance = DatabaseManager()
    return _db_manager_instance
