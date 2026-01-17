"""
A_mind启动处理器
"""
from pathlib import Path
from typing import List

from src.plugin_system import BaseEventHandler, EventType
from src.manager.async_task_manager import async_task_manager

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
try:
    from ..handlers.auto_initiate_action import AutoInitiateAction
    from ..services.auto_sender import AutoSender
    from ..core.a_mind_plan_tick_task import AMindPlanTickTask
except ImportError:
    # 直接导入时的备用方案
    import sys
    from pathlib import Path
    # 添加插件路径到sys.path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from handlers.auto_initiate_action import AutoInitiateAction
    from services.auto_sender import AutoSender
    from core.a_mind_plan_tick_task import AMindPlanTickTask

logger = get_logger(__name__)


class AMindStartHandler(BaseEventHandler):
    event_type = EventType.ON_START
    handler_name = "a_mind_on_start"
    handler_description = "A_Mind 启动时启动 Plan-1 周期任务"

    def get_config(self, key: str, default=None):
        """获取配置"""
        # 首先尝试从plugin_config获取
        if self.plugin_config:
            keys = key.split('.')
            current = self.plugin_config
            try:
                for k in keys:
                    current = current[k]
                logger.debug(f"Found {key} in plugin_config: {current}")
                return current
            except (KeyError, TypeError) as e:
                logger.debug(f"{key} not found in plugin_config: {e}")
                pass

        # 如果plugin_config不可用，尝试直接读取config.toml文件
        try:
            import toml
            config_path = Path(__file__).parent.parent / "config.toml"
            if config_path.exists():
                config = toml.load(config_path)
                keys = key.split('.')
                current = config
                for k in keys:
                    current = current[k]
                logger.debug(f"Found {key} in config.toml: {current}")
                return current
        except Exception as e:
            logger.debug(f"Error reading config.toml for {key}: {e}")
            pass

        logger.debug(f"Using default for {key}: {default}")
        return default

    def _get_available_plans(self) -> List[str]:
        """获取所有可用的plan配置"""
        try:
            # 尝试从plugin_config获取
            if self.plugin_config:
                plan_names = []
                for key in self.plugin_config.keys():
                    if key.startswith('plan') and key != 'plan1':  # plan1单独处理
                        if isinstance(self.plugin_config[key], dict) and self.plugin_config[key].get('enabled', False):
                            plan_names.append(key)
                # 总是包含plan1（如果存在）
                if 'plan1' in self.plugin_config and isinstance(self.plugin_config['plan1'], dict):
                    plan_names.insert(0, 'plan1')
                return plan_names

            # 如果plugin_config不可用，尝试直接读取config.toml文件
            try:
                import toml
                config_path = Path(__file__).parent.parent / "config.toml"
                if config_path.exists():
                    config = toml.load(config_path)
                    plan_names = []
                    for key in config.keys():
                        if key.startswith('plan') and isinstance(config[key], dict):
                            if config[key].get('enabled', False):
                                plan_names.append(key)
                    return sorted(plan_names)  # 按名称排序
            except Exception:
                pass

            return []
        except Exception as e:
            logger.error(f"[A_mind] 获取可用plans失败: {e}")
            return []

    async def execute(self, message):
        try:
            # 获取所有可用的plan配置
            available_plans = self._get_available_plans()
            logger.info(f"[A_mind] 发现 {len(available_plans)} 个启用的plan配置: {available_plans}")

            if not available_plans:
                logger.info("[A_mind] 未发现任何启用的plan配置")
                return True, True, None, None, None

            # 为每个plan创建对应的任务
            for plan_name in available_plans:
                try:
                    logger.info(f"[A_mind] 正在初始化 {plan_name} 任务")

                    # 用 action 来复用现有自发起工作流
                    # 为AutoInitiateAction提供必要的初始化参数（启动时不需要真实的参数）
                    class _DummyChatStream:
                        def __init__(self):
                            self.stream_id = f"{plan_name}_startup"

                    dummy_action_data = {}
                    dummy_action_reasoning = f"{plan_name}_startup"
                    dummy_cycle_timers = {}
                    dummy_thinking_id = f"{plan_name}_init"
                    dummy_chat_stream = _DummyChatStream()

                    # 创建dummy action_message，避免BaseAction初始化时的chat_info访问错误
                    class _DummyUserInfo:
                        def __init__(self):
                            self.user_id = "system"
                            self.user_nickname = "System"

                    class _DummyGroupInfo:
                        def __init__(self):
                            self.group_id = None
                            self.group_name = None

                    class _DummyChatInfo:
                        def __init__(self):
                            self.group_info = _DummyGroupInfo()

                    class _DummyActionMessage:
                        def __init__(self):
                            self.chat_info = _DummyChatInfo()
                            self.user_info = _DummyUserInfo()

                    dummy_action_message = _DummyActionMessage()

                    # 创建 AutoInitiateAction 实例
                    auto_initiate = AutoInitiateAction(
                        action_data=dummy_action_data,
                        action_reasoning=dummy_action_reasoning,
                        cycle_timers=dummy_cycle_timers,
                        thinking_id=dummy_thinking_id,
                        chat_stream=dummy_chat_stream,
                        action_message=dummy_action_message,
                        plan_name=plan_name,  # 传递plan名称用于模型配置
                    )

                    # 设置container引用，使服务能够从依赖注入容器正确初始化
                    try:
                        from ..plugin import _plugin_instance
                        if _plugin_instance and hasattr(_plugin_instance, 'container'):
                            auto_initiate.container = _plugin_instance.container
                        else:
                            # 如果无法获取container，设置一个能够读取config.toml的配置管理器
                            class ConfigManager:
                                def __init__(self, config_getter):
                                    self._get_config = config_getter

                                def get(self, key, default=None):
                                    return self._get_config(key, default)

                                def get_model_config(self, plan_name=None, service_name=None):
                                    """获取模型配置"""
                                    return {
                                        "model_name": self.get("llm.model_name", "tool_use"),
                                        "fallback_model_name": self.get("llm.fallback_model_name", "tool_use"),
                                        "temperature": self.get("llm.temperature", 0.7),
                                        "max_tokens": self.get("llm.max_tokens", 1500),
                                    }

                            auto_initiate.config_manager = ConfigManager(self.get_config)
                    except Exception:
                        pass  # 如果无法设置container，服务会使用备用方案

                    # 设置一个dummy message，避免任何访问message属性的代码出错
                    class _DummyMessage:
                        def __init__(self):
                            self.chat_stream = dummy_chat_stream
                            self.message_info = None
                            self.plain_text = ""
                            self.processed_plain_text = ""

                    auto_initiate.message = _DummyMessage()

                    # AutoSender 用于处理队列
                    auto_sender = AutoSender()
                    auto_sender.get_config = self.get_config

                    # 创建对应的任务
                    task = AMindPlanTickTask(
                        plan_name=plan_name,
                        get_config=self.get_config,
                        auto_sender=auto_sender,
                        auto_initiate_action=auto_initiate,
                    )
                    await async_task_manager.add_task(task)
                    logger.info(f"[A_mind] {plan_name} 任务创建成功")

                except Exception as e:
                    logger.error(f"[A_mind] 创建 {plan_name} 任务失败: {e}")
                    continue

            return True, True, None, None, None
        except Exception as e:
            logger.error(f"[A_mind] ON_START handler failed: {e}")
            return True, True, None, None, None
