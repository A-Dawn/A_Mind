"""
A_Mind计划Tick任务
"""
from typing import Callable
import asyncio
import random
import time

from src.manager.async_task_manager import AsyncTask

# Logger import with fallback
try:
    from .amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
from ..services.auto_sender import AutoSender
from ..handlers.auto_initiate_action import AutoInitiateAction
from ..handlers.topic_capture_action import TopicCaptureAction
from ..utils import resolve_stream_config_to_stream_id

logger = get_logger(__name__)


class AMindPlanTickTask(AsyncTask):
    def __init__(
        self,
        plan_name: str,
        get_config: Callable,
        auto_sender: AutoSender,
        auto_initiate_action: AutoInitiateAction,
        plan_name_for_action: str = None,
    ):
        self._plan_name = plan_name
        self._get_config = get_config
        self._auto_sender = auto_sender
        self._auto_initiate_action = auto_initiate_action

        self._lock = asyncio.Lock()
        self._last_auto_initiate_at: float = 0

        super().__init__(
            task_name=f"A_Mind{plan_name.capitalize()}TickTask",
            wait_before_start=0,
            run_interval=int(get_config(f"{plan_name}.tick_interval_seconds", 30)),
        )

        # 记录启动时间
        self._startup_time = time.time()
        # 尝试从数据库加载上次执行时间
        try:
            from ..utils import get_global_db_manager
            db_mgr = get_global_db_manager()
            last_time_str = db_mgr.get_meta(f"last_initiate_{plan_name}")
            if last_time_str:
                self._last_auto_initiate_at = float(last_time_str)
                logger.info(f"[A_Mind] 已加载 {plan_name} 上次发起时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_auto_initiate_at))}")
        except Exception as e:
            logger.warning(f"[A_Mind] 加载上次发起时间失败: {e}")

    async def run(self):
        plan_display = self._plan_name.upper()
        # logger.debug(f"[{plan_display}] Tick执行开始 - {time.strftime('%H:%M:%S', time.localtime())}")

        # 1) 启动热身期检查（防止开机即发）
        startup_delay = 60  # 60秒热身期
        if time.time() - self._startup_time < startup_delay:
            # logger.debug(f"[{plan_display}] 启动热身中，跳过执行")
            return

        # 2) 免打扰时段检查
        if self._is_dnd_active():
            logger.debug(f"[{plan_display}] 当前处于免打扰时段，跳过执行")
            return

        # 3) 处理 AutoSender 队列
        try:
            await self._auto_sender.process_queue()
            # logger.debug(f"[{plan_display}] AutoSender队列处理完成")
        except Exception as e:
            logger.error(f"[{plan_display}] AutoSender队列处理失败: {e}")

        # 4) 检查是否启用当前plan
        enabled = bool(self._get_config(f"{self._plan_name}.enabled", False))
        if not enabled:
            return

        stream_config = str(self._get_config(f"{self._plan_name}.stream_config", "")).strip()
        if not stream_config:
            logger.warning(f"[{plan_display}] 聊天流配置为空，跳过本次执行")
            return

        stream_id = self._parse_stream_config_to_stream_id(stream_config)
        if not stream_id:
            logger.warning(f"[{plan_display}] stream_config无效: {stream_config}")
            return

        # AutoInitiateAction 依赖 self.message.chat_stream.stream_id，因此这里构造一个最小 message
        class _PlanChatStream:
            def __init__(self, sid: str):
                self.stream_id = sid

        class _PlanMessage:
            def __init__(self, sid: str):
                self.chat_stream = _PlanChatStream(sid)

        self._auto_initiate_action.message = _PlanMessage(stream_id)  # type: ignore

        # 5) 概率触发 + 冷却（自动发起）
        cooldown_seconds = int(self._get_config(f"{self._plan_name}.cooldown_seconds", 1800))
        prob = float(self._get_config(f"{self._plan_name}.trigger_probability", 0.02))
        now = time.time()

        if self._last_auto_initiate_at == 0:
            try:
                from ..utils import get_global_db_manager

                db_mgr = get_global_db_manager()
                last_time_str = db_mgr.get_meta(f"last_initiate_{self._plan_name}")
                if last_time_str:
                    self._last_auto_initiate_at = float(last_time_str)
                    logger.info(
                        f"[{plan_display}] 重新加载上次发起时间成功: "
                        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_auto_initiate_at))}"
                    )
            except Exception:
                pass

        should_try_auto_initiate = True
        if self._last_auto_initiate_at and (now - self._last_auto_initiate_at) < cooldown_seconds:
            should_try_auto_initiate = False
        elif random.random() >= prob:
            should_try_auto_initiate = False

        if should_try_auto_initiate:
            logger.info(f"[{plan_display}] 通过概率检查，开始执行自动发起")
            async with self._lock:
                now = time.time()
                if self._last_auto_initiate_at and (now - self._last_auto_initiate_at) < cooldown_seconds:
                    logger.warning(f"[{plan_display}] 并发检查：仍在冷却中")
                else:
                    ok, msg = await self._auto_initiate_action.execute()
                    now_ts = time.time()
                    self._last_auto_initiate_at = now_ts

                    try:
                        from ..utils import get_global_db_manager

                        db_mgr = get_global_db_manager()
                        db_mgr.set_meta(f"last_initiate_{self._plan_name}", str(now_ts))
                    except Exception as e:
                        logger.warning(f"[{plan_display}] 持久化时间戳失败: {e}")

                    if ok:
                        logger.info(f"[{plan_display}] ✅ 自动发起成功: {msg}")
                    else:
                        logger.warning(f"[{plan_display}] ❌ 自动发起失败: {msg}")

        # 6) 话题捕捉（独立于自动发起触发）
        try:
            capture_enabled = bool(self._get_config(f"{self._plan_name}.topic_capture.enabled", False))
            if capture_enabled:
                capture_interval = int(self._get_config(f"{self._plan_name}.topic_capture.interval", 600))
                capture_prob = float(self._get_config(f"{self._plan_name}.topic_capture.probability", 0.5))

                now = time.time()
                last_capture = getattr(self, "_last_capture_at", 0)
                if (now - last_capture) >= capture_interval and random.random() < capture_prob:
                    logger.info(f"[{plan_display}] 触发话题捕捉检查...")
                    capture_action = TopicCaptureAction(
                        action_data={},
                        action_reasoning=f"Topic Capture via {self._plan_name}",
                        cycle_timers={},
                        thinking_id=f"capture_{int(now)}",
                        chat_stream=self._auto_initiate_action.message.chat_stream,
                        action_message=self._auto_initiate_action.action_message,
                        plan_name=self._plan_name,
                        auto_initiate_action=self._auto_initiate_action,
                    )

                    cap_ok, cap_msg = await capture_action.execute()
                    self._last_capture_at = time.time()
                    if cap_ok:
                        logger.info(f"[{plan_display}] 🎯 话题捕捉并在群内发言: {cap_msg}")
        except Exception as e:
            logger.error(f"[{plan_display}] 话题捕捉逻辑出错: {e}")

    def _parse_stream_config_to_stream_id(self, stream_config_str: str) -> str:
        """从 `platform:id:type` 解析 stream_id。

        例："qq:123456:group" / "qq:123456:private"。
        """
        try:
            return resolve_stream_config_to_stream_id(stream_config_str)

        except Exception:
            return ""

    def _is_dnd_active(self) -> bool:
        """检查当前是否处于免打扰时段"""
        try:
            # 获取DND配置 (注意：在config_schema中，dnd配置位于topic_management下，但get_config可能直接访问)
            # 根据plugin.py结构，dnd配置在topic_management下
            # 但get_config实现通常支持 key.subkey
            enabled = self._get_config("topic_management.dnd_enabled", False)
            if not enabled:
                return False

            start_str = str(self._get_config("topic_management.dnd_start_time", "23:00"))
            end_str = str(self._get_config("topic_management.dnd_end_time", "08:00"))

            # 解析时间
            current_time = time.localtime()
            current_hour = current_time.tm_hour
            current_minute = current_time.tm_min
            current_val = current_hour * 60 + current_minute

            try:
                sh, sm = map(int, start_str.split(":"))
                start_val = sh * 60 + sm
                
                eh, em = map(int, end_str.split(":"))
                end_val = eh * 60 + em
            except ValueError:
                logger.warning(f"DND时间格式错误: start={start_str}, end={end_str}，应为 HH:MM")
                return False

            # 判断逻辑
            if start_val < end_val:
                # 同一天内 (例如 09:00 - 12:00)
                return start_val <= current_val < end_val
            else:
                # 跨天 (例如 23:00 - 08:00)
                # 此时有两种情况：
                # 1. 还没过午夜 (23:30 > 23:00)
                # 2. 过了午夜 (00:30 < 08:00)
                return current_val >= start_val or current_val < end_val

        except Exception as e:
            logger.error(f"DND检查出错: {e}")
            return False
