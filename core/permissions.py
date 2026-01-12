"""
权限管理器

处理用户权限验证和管理
"""

from typing import List, Optional, Callable, Any
from functools import wraps


class PermissionManager:
    """权限管理器 - 处理用户权限验证"""

    # 权限级别定义
    PERMISSION_LEVELS = {
        'user': 0,
        'admin': 1,
        'super_admin': 2,
        'debug': 3
    }

    def __init__(self, config_manager):
        """初始化权限管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config = config_manager

    def has_permission(self, user_id: str, required_level: str = "user") -> bool:
        """检查用户是否有指定权限

        Args:
            user_id: 用户ID
            required_level: 需要的权限级别

        Returns:
            是否有权限
        """
        user_level = self.get_user_permission_level(user_id)
        required_level_value = self.PERMISSION_LEVELS.get(required_level, 0)

        return user_level >= required_level_value

    def get_user_permission_level(self, user_id: str) -> int:
        """获取用户权限级别

        Args:
            user_id: 用户ID

        Returns:
            权限级别数值
        """
        # 检查超级管理员
        super_admins = self.config.get_list("permissions.super_admins", [])
        if user_id in super_admins:
            return self.PERMISSION_LEVELS['super_admin']

        # 检查调试用户
        debug_users = self.config.get_list("debug.allowed_debug_users", [])
        if user_id in debug_users:
            return self.PERMISSION_LEVELS['debug']

        # 检查全局管理员模式
        if self.config.get_bool("permissions.global_admin_mode", False):
            return self.PERMISSION_LEVELS['admin']

        # 检查管理员群组成员
        # 这里需要根据实际的群组成员检查逻辑来实现
        # 暂时返回普通用户权限
        return self.PERMISSION_LEVELS['user']

    def is_super_admin(self, user_id: str) -> bool:
        """检查是否为超级管理员"""
        return self.has_permission(user_id, "super_admin")

    def is_admin(self, user_id: str) -> bool:
        """检查是否为管理员"""
        return self.has_permission(user_id, "admin")

    def is_debug_user(self, user_id: str) -> bool:
        """检查是否为调试用户"""
        return self.has_permission(user_id, "debug")

    def get_permission_name(self, level: int) -> str:
        """获取权限级别的名称

        Args:
            level: 权限级别数值

        Returns:
            权限级别名称
        """
        for name, value in self.PERMISSION_LEVELS.items():
            if value == level:
                return name
        return 'user'

    def validate_admin_access(self, user_id: str, operation: str = "") -> None:
        """验证管理员访问权限

        Args:
            user_id: 用户ID
            operation: 操作名称（用于错误信息）

        Raises:
            PermissionError: 无权限时抛出异常
        """
        if not self.is_admin(user_id):
            operation_desc = f" for operation '{operation}'" if operation else ""
            raise PermissionError(f"User {user_id} does not have admin permission{operation_desc}")

    def validate_debug_access(self, user_id: str, operation: str = "") -> None:
        """验证调试访问权限

        Args:
            user_id: 用户ID
            operation: 操作名称（用于错误信息）

        Raises:
            PermissionError: 无权限时抛出异常
        """
        if not self.is_debug_user(user_id):
            operation_desc = f" for operation '{operation}'" if operation else ""
            raise PermissionError(f"User {user_id} does not have debug permission{operation_desc}")


def require_permission(permission_level: str = "admin"):
    """权限检查装饰器 - 用于A_Mind命令"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                # 获取权限管理器 - 从容器或全局实例获取
                permission_manager = None

                # 尝试从self.container获取（如果有的话）
                if hasattr(self, 'container') and self.container and hasattr(self.container, 'permission_manager'):
                    permission_manager = self.container.permission_manager
                else:
                    # 从全局插件实例获取
                    try:
                        from ..plugin import _plugin_instance
                    except ImportError:
                        # 如果有循环导入问题，暂时跳过
                        _plugin_instance = None
                    if _plugin_instance and hasattr(_plugin_instance, 'container'):
                        permission_manager = _plugin_instance.container.permission_manager

                if permission_manager is None:
                    # 如果无法获取权限管理器，记录警告但允许执行（向后兼容）
                    try:
                        from .amind_logger import get_logger
                    except ImportError:
                        from core.amind_logger import get_logger
                    logger = get_logger(__name__)
                    logger.warning(f"[A_Mind] 无法获取权限管理器，跳过权限检查: {permission_level}")
                    return await func(self, *args, **kwargs)

                # 从消息上下文中获取用户ID
                user_id = None
                if hasattr(self, 'message') and self.message:
                    # 尝试从消息中提取用户ID
                    if hasattr(self.message, 'sender') and hasattr(self.message.sender, 'user_id'):
                        user_id = str(self.message.sender.user_id)
                    elif hasattr(self.message, 'user_id'):
                        user_id = str(self.message.user_id)

                if user_id is None:
                    # 如果无法获取用户ID，记录警告但允许执行
                    try:
                        from .amind_logger import get_logger
                    except ImportError:
                        from core.amind_logger import get_logger
                    logger = get_logger(__name__)
                    logger.warning(f"[A_Mind] 无法获取用户ID，跳过权限检查: {permission_level}")
                    return await func(self, *args, **kwargs)

                # 执行权限检查
                if not permission_manager.has_permission(user_id, permission_level):
                    return False, f"权限不足：需要 {permission_level} 权限", False

                # 权限检查通过，执行原函数
                return await func(self, *args, **kwargs)

            except Exception as e:
                # 权限检查出错时记录错误但允许执行
                try:
                    from .amind_logger import get_logger
                except ImportError:
                    from core.amind_logger import get_logger
                logger = get_logger(__name__)
                logger.error(f"[A_Mind] 权限检查失败: {e}")
                return await func(self, *args, **kwargs)

        return wrapper

    return decorator
