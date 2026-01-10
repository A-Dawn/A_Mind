"""
依赖注入容器

管理组件间的依赖关系和生命周期
"""

from ..repositories.database_manager import DatabaseManager
from ..repositories.topic_repository import TopicRepository
from ..repositories.reply_repository import ReplyRepository
# Services will be imported when needed to avoid circular imports
from .config_manager import ConfigManager
from .permissions import PermissionManager


class DependencyContainer:
    """依赖注入容器 - 管理所有组件的创建和依赖注入"""

    def __init__(self, plugin_instance):
        """初始化依赖容器

        Args:
            plugin_instance: 插件实例
        """
        self.plugin = plugin_instance
        self._config_manager = None
        self._permission_manager = None
        self._database_manager = None
        self._topic_repository = None
        self._reply_repository = None
        self._information_retriever = None
        self._brainstorm_generator = None
        self._decision_selector = None
        self._auto_sender = None
        self._response_monitor = None

    @property
    def config_manager(self) -> ConfigManager:
        """配置管理器"""
        if self._config_manager is None:
            self._config_manager = ConfigManager(self.plugin)
        return self._config_manager

    @property
    def permission_manager(self) -> PermissionManager:
        """权限管理器"""
        if self._permission_manager is None:
            self._permission_manager = PermissionManager(self.config_manager)
        return self._permission_manager

    @property
    def database_manager(self) -> DatabaseManager:
        """数据库管理器"""
        if self._database_manager is None:
            self._database_manager = DatabaseManager()
        return self._database_manager

    @property
    def topic_repository(self) -> TopicRepository:
        """话题数据仓库"""
        if self._topic_repository is None:
            self._topic_repository = TopicRepository(self.database_manager)
        return self._topic_repository

    @property
    def reply_repository(self) -> ReplyRepository:
        """回复数据仓库"""
        if self._reply_repository is None:
            self._reply_repository = ReplyRepository(self.database_manager)
        return self._reply_repository

    @property
    def information_retriever(self):
        """信息检索器"""
        if self._information_retriever is None:
            from ..services.information_retriever import InformationRetriever
            self._information_retriever = InformationRetriever(self.config_manager)
        return self._information_retriever

    @property
    def brainstorm_generator(self):
        """头脑风暴生成器"""
        if self._brainstorm_generator is None:
            from ..services.brainstorm_generator import BrainstormGenerator
            self._brainstorm_generator = BrainstormGenerator(self.config_manager)
        return self._brainstorm_generator

    def get_brainstorm_generator(self, plan_name: str = None):
        """获取头脑风暴生成器，支持指定plan配置"""
        from ..services.brainstorm_generator import BrainstormGenerator
        return BrainstormGenerator(self.config_manager, plan_name)

    @property
    def decision_selector(self):
        """决策选择器"""
        if self._decision_selector is None:
            from ..services.decision_selector import DecisionSelector
            self._decision_selector = DecisionSelector(self.config_manager)
        return self._decision_selector

    def get_decision_selector(self, plan_name: str = None):
        """获取决策选择器，支持指定plan配置"""
        from ..services.decision_selector import DecisionSelector
        return DecisionSelector(self.config_manager, plan_name)

    @property
    def auto_sender(self):
        """自动发送器"""
        if self._auto_sender is None:
            from ..services.auto_sender import AutoSender
            self._auto_sender = AutoSender(self.database_manager)
        return self._auto_sender

    @property
    def response_monitor(self):
        """响应监测器"""
        if self._response_monitor is None:
            from ..services.response_monitor import ResponseMonitor
            self._response_monitor = ResponseMonitor()
        return self._response_monitor

    def get_service(self, service_name: str):
        """获取服务实例

        Args:
            service_name: 服务名称

        Returns:
            服务实例
        """
        service_map = {
            'config_manager': self.config_manager,
            'permission_manager': self.permission_manager,
            'database_manager': self.database_manager,
            'topic_repository': self.topic_repository,
            'reply_repository': self.reply_repository,
            'information_retriever': self.information_retriever,
            'brainstorm_generator': self.brainstorm_generator,
            'decision_selector': self.decision_selector,
            'auto_sender': self.auto_sender,
            'response_monitor': self.response_monitor,
        }

        return service_map.get(service_name)

    def dispose(self):
        """清理资源"""
        # 这里可以添加资源清理逻辑
        pass
