"""
A_mind启动处理器
"""
from pathlib import Path
from typing import Callable, Dict, List, Optional

from maibot_sdk.compat import BaseEventHandler, EventType
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
    from ..core.a_mind_global_pool_tick_task import AMindGlobalPoolTickTask
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
    from core.a_mind_global_pool_tick_task import AMindGlobalPoolTickTask

logger = get_logger(__name__)


GLOBAL_POOL_TASK_NAME = "A_MindGlobalPoolTickTask"


def get_amind_plan_task_name(plan_name: str) -> str:
    return f"A_Mind{str(plan_name or '').capitalize()}TickTask"


def _get_nested_config(config: Dict, key: str, default=None):
    current = config
    for part in str(key or "").split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def make_amind_config_getter(plugin_config: Optional[Dict] = None) -> Callable:
    config_data = plugin_config if isinstance(plugin_config, dict) else {}

    def get_config(key: str, default=None):
        """获取配置"""
        value = _get_nested_config(config_data, key, None)
        if value is not None:
            logger.debug(f"Found {key} in plugin_config: {value}")
            return value

        try:
            import toml

            config_path = Path(__file__).parent.parent / "config.toml"
            if config_path.exists():
                value = _get_nested_config(toml.load(config_path), key, None)
                if value is not None:
                    logger.debug(f"Found {key} in config.toml: {value}")
                    return value
        except Exception as e:
            logger.debug(f"Error reading config.toml for {key}: {e}")

        logger.debug(f"Using default for {key}: {default}")
        return default

    return get_config


def get_available_amind_plans(plugin_config: Optional[Dict] = None) -> List[str]:
    """获取所有已启用的 plan 配置。"""
    try:
        config_data = plugin_config if isinstance(plugin_config, dict) else {}
        if not config_data:
            try:
                import toml

                config_path = Path(__file__).parent.parent / "config.toml"
                if config_path.exists():
                    config_data = toml.load(config_path)
            except Exception:
                config_data = {}

        plan_names = []
        for key in config_data.keys():
            if key.startswith("plan") and isinstance(config_data[key], dict):
                if config_data[key].get("enabled", False):
                    plan_names.append(key)
        return sorted(plan_names)
    except Exception as e:
        logger.error(f"[A_mind] 获取可用plans失败: {e}")
        return []


async def refresh_amind_background_tasks(
    plugin_config: Optional[Dict] = None,
    get_config: Optional[Callable] = None,
    *,
    legacy_plugin=None,
    plugin_id: str = "",
) -> List[str]:
    get_config = get_config or make_amind_config_getter(plugin_config)
    plugin_id = str(plugin_id or _get_current_plugin_id() or "")

    available_plans = get_available_amind_plans(plugin_config)
    logger.info(f"[A_mind] 发现 {len(available_plans)} 个启用的plan配置: {available_plans}")

    if not available_plans:
        logger.info("[A_mind] 未发现任何启用的plan配置")

    await _stop_disabled_plan_tasks(available_plans)

    for plan_name in available_plans:
        try:
            logger.info(f"[A_mind] 正在初始化 {plan_name} 任务")

            class _DummyChatStream:
                def __init__(self):
                    self.stream_id = f"{plan_name}_startup"

            dummy_action_data = {}
            dummy_action_reasoning = f"{plan_name}_startup"
            dummy_cycle_timers = {}
            dummy_thinking_id = f"{plan_name}_init"
            dummy_chat_stream = _DummyChatStream()

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

            auto_initiate = AutoInitiateAction(
                action_data=dummy_action_data,
                action_reasoning=dummy_action_reasoning,
                cycle_timers=dummy_cycle_timers,
                thinking_id=dummy_thinking_id,
                chat_stream=dummy_chat_stream,
                action_message=dummy_action_message,
                plan_name=plan_name,
            )

            container_owner = legacy_plugin
            if container_owner is None:
                try:
                    from ..plugin import _plugin_instance

                    container_owner = _plugin_instance
                except Exception:
                    container_owner = None

            if container_owner is not None and hasattr(container_owner, "container"):
                auto_initiate.container = container_owner.container
                auto_initiate.config_manager = container_owner.container.config_manager
            else:
                class ConfigManager:
                    def __init__(self, config_getter):
                        self._get_config = config_getter

                    def get(self, key, default=None):
                        return self._get_config(key, default)

                    def get_model_config(self, plan_name=None, service_name=None):
                        return {
                            "model_name": self.get("llm.model_name", "utils"),
                            "fallback_model_name": self.get("llm.fallback_model_name", "replyer"),
                            "temperature": self.get("llm.temperature", 0.7),
                            "max_tokens": self.get("llm.max_tokens", 1500),
                        }

                auto_initiate.config_manager = ConfigManager(get_config)

            class _DummyMessage:
                def __init__(self):
                    self.chat_stream = dummy_chat_stream
                    self.message_info = None
                    self.plain_text = ""
                    self.processed_plain_text = ""

            auto_initiate.message = _DummyMessage()

            auto_sender = AutoSender()
            auto_sender.get_config = get_config

            task = AMindPlanTickTask(
                plan_name=plan_name,
                get_config=get_config,
                auto_sender=auto_sender,
                auto_initiate_action=auto_initiate,
                plugin_id=plugin_id,
            )
            await async_task_manager.add_task(task)
            logger.info(f"[A_mind] {plan_name} 任务创建成功")

        except Exception as e:
            logger.error(f"[A_mind] 创建 {plan_name} 任务失败: {e}")
            continue

    try:
        global_pool_sender = AutoSender()
        global_pool_sender.get_config = get_config
        global_pool_task = AMindGlobalPoolTickTask(
            get_config=get_config,
            auto_sender=global_pool_sender,
            plugin_id=plugin_id,
        )
        await async_task_manager.add_task(global_pool_task)
        logger.info("[A_mind] 总控池任务创建成功")
    except Exception as e:
        logger.error(f"[A_mind] 创建总控池任务失败: {e}")

    return available_plans


def _get_current_plugin_id() -> str:
    try:
        from maibot_sdk.compat import _context_holder

        ctx = _context_holder.get_context()
        return str(getattr(ctx, "plugin_id", "") or "")
    except Exception:
        return ""


async def stop_amind_background_tasks() -> None:
    """停止 A_Mind 已注册的后台任务。"""
    task_names = [
        name
        for name in list(getattr(async_task_manager, "tasks", {}).keys())
        if name.startswith("A_Mind") and name.endswith("TickTask")
    ]
    for task_name in task_names:
        await _cancel_task_by_name(task_name)


async def _stop_disabled_plan_tasks(enabled_plans: List[str]) -> None:
    enabled_task_names = {get_amind_plan_task_name(plan_name) for plan_name in enabled_plans}
    current_task_names = list(getattr(async_task_manager, "tasks", {}).keys())
    for task_name in current_task_names:
        if not (task_name.startswith("A_Mind") and task_name.endswith("TickTask")):
            continue
        if task_name == GLOBAL_POOL_TASK_NAME:
            continue
        if task_name not in enabled_task_names:
            await _cancel_task_by_name(task_name)


async def _cancel_task_by_name(task_name: str) -> None:
    task_map = getattr(async_task_manager, "tasks", {})
    task = task_map.get(task_name)
    if task is None:
        return

    task.cancel()
    try:
        await task
    except BaseException as exc:
        if exc.__class__.__name__ != "CancelledError":
            logger.warning(f"[A_mind] 取消后台任务 {task_name} 时发生异常: {exc}")
    if task_map.get(task_name) is task:
        task_map.pop(task_name, None)


class AMindStartHandler(BaseEventHandler):
    event_type = EventType.ON_START
    handler_name = "a_mind_on_start"
    handler_description = "A_Mind 启动时启动后台周期任务"

    def get_config(self, key: str, default=None):
        return make_amind_config_getter(getattr(self, "plugin_config", None))(key, default)

    def _get_available_plans(self) -> List[str]:
        return get_available_amind_plans(getattr(self, "plugin_config", None))

    async def execute(self, message):
        try:
            plugin_config = getattr(self, "plugin_config", None)
            await refresh_amind_background_tasks(
                plugin_config=plugin_config,
                get_config=make_amind_config_getter(plugin_config),
            )
            return True, True, None, None, None
        except Exception as e:
            logger.error(f"[A_mind] ON_START handler failed: {e}")
            return True, True, None, None, None
