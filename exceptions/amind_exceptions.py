"""
A_Mind插件自定义异常类

定义插件中使用的所有异常类型
"""


class AMindError(Exception):
    """A_Mind基础异常类"""
    pass


class DatabaseError(AMindError):
    """数据库相关异常"""
    pass


class LLMError(AMindError):
    """LLM调用相关异常"""
    pass


class PermissionError(AMindError):
    """权限相关异常"""
    pass


class ConfigurationError(AMindError):
    """配置相关异常"""
    pass


class ValidationError(AMindError):
    """数据验证异常"""
    pass


class TopicNotFoundError(AMindError):
    """话题未找到异常"""

    def __init__(self, topic_id: int):
        self.topic_id = topic_id
        super().__init__(f"Topic with id {topic_id} not found")


class StreamAccessError(AMindError):
    """聊天流访问异常"""

    def __init__(self, stream_id: str, topic_id: int = None):
        self.stream_id = stream_id
        self.topic_id = topic_id
        if topic_id:
            super().__init__(f"Stream {stream_id} does not have access to topic {topic_id}")
        else:
            super().__init__(f"Stream {stream_id} access denied")


class AutoInitiateError(AMindError):
    """自动发起相关异常"""
    pass


class MonitoringError(AMindError):
    """监控相关异常"""
    pass
