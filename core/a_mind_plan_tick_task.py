"""
A_Mind计划Tick任务
"""
import asyncio
import random
import time
from typing import Callable

from src.common.logger import get_logger
from src.manager.async_task_manager import AsyncTask
from ..services.auto_sender import AutoSender
from ..handlers.auto_initiate_action import AutoInitiateAction

logger = get_logger("A_Mind")


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

    async def run(self):
        plan_display = self._plan_name.upper()
        print(f"[A_Mind][{plan_display}] Tick执行开始 - {time.strftime('%H:%M:%S', time.localtime())}")

        # 1) 处理 AutoSender 队列
        try:
            await self._auto_sender.process_queue()
            print(f"[A_Mind][{plan_display}] AutoSender队列处理完成")
        except Exception as e:
            print(f"[A_Mind][{plan_display}] process_queue失败: {e}")
            logger.error(f"[A_Mind][{plan_display}] process_queue failed: {e}")

        # 2) 概率触发 + 冷却
        enabled = bool(self._get_config(f"{self._plan_name}.enabled", False))
        print(f"[A_Mind][{plan_display}] {self._plan_name.upper()}启用状态: {enabled}")
        if not enabled:
            print(f"[A_Mind][{plan_display}] {self._plan_name.upper()}未启用，跳过自动发起")
            return

        cooldown_seconds = int(self._get_config(f"{self._plan_name}.cooldown_seconds", 1800))
        prob = float(self._get_config(f"{self._plan_name}.trigger_probability", 0.02))
        now = time.time()

        print(f"[A_Mind][{plan_display}] 配置 - 冷却时间:{cooldown_seconds}秒, 触发概率:{prob}")

        if self._last_auto_initiate_at and (now - self._last_auto_initiate_at) < cooldown_seconds:
            remaining = int(cooldown_seconds - (now - self._last_auto_initiate_at))
            print(f"[A_Mind][{plan_display}] 冷却中，还需等待{remaining}秒")
            return

        random_value = random.random()
        print(f"[A_Mind][{plan_display}] 随机值:{random_value:.3f}, 触发阈值:{prob}")
        if random_value >= prob:
            print(f"[A_Mind][{plan_display}] 未触发概率检查，跳过本次执行")
            return

        print(f"[A_Mind][{plan_display}] 通过概率检查，开始执行自动发起")

        async with self._lock:
            now = time.time()
            if self._last_auto_initiate_at and (now - self._last_auto_initiate_at) < cooldown_seconds:
                print(f"[A_Mind][{plan_display}] 并发检查：仍在冷却中")
                return

            stream_config = str(self._get_config(f"{self._plan_name}.stream_config", "")).strip()
            print(f"[A_Mind][{plan_display}] 聊天流配置: '{stream_config}'")
            if not stream_config:
                print(f"[A_Mind][{plan_display}] 聊天流配置为空，跳过自动发起")
                logger.warning(f"[A_Mind][{plan_display}] stream_config empty; skip auto initiate")
                return

            stream_id = self._parse_stream_config_to_stream_id(stream_config)
            print(f"[A_Mind][{plan_display}] 解析得到stream_id: '{stream_id}'")
            if not stream_id:
                print(f"[A_Mind][{plan_display}] stream_config无效: {stream_config}")
                logger.warning(f"[A_Mind][{plan_display}] invalid stream_config: {stream_config}")
                return

            print(f"[A_Mind][{plan_display}] 开始执行自动发起，目标聊天流: {stream_id}")

            # AutoInitiateAction 依赖 self.message.chat_stream.stream_id，因此这里构造一个最小 message
            class _PlanChatStream:
                def __init__(self, sid: str):
                    self.stream_id = sid

            class _PlanMessage:
                def __init__(self, sid: str):
                    self.chat_stream = _PlanChatStream(sid)

            self._auto_initiate_action.message = _PlanMessage(stream_id)  # type: ignore

            ok, msg = await self._auto_initiate_action.execute()
            if ok:
                self._last_auto_initiate_at = time.time()
                print(f"[A_Mind][{plan_display}] ✅ 自动发起成功: {msg}")
                logger.info(f"[A_Mind][{plan_display}] auto initiate ok: {msg}")
            else:
                print(f"[A_Mind][{plan_display}] ❌ 自动发起失败: {msg}")
                logger.warning(f"[A_Mind][{plan_display}] auto initiate failed: {msg}")

    def _parse_stream_config_to_stream_id(self, stream_config_str: str) -> str:
        """从 `platform:id:type` 解析 stream_id。

        例："qq:123456:group" / "qq:123456:private"。
        """
        try:
            parts = stream_config_str.split(":")
            if len(parts) != 3:
                return ""

            platform, id_str, stream_type = parts
            is_group = stream_type == "group"

            from src.chat.message_receive.chat_stream import get_chat_manager

            stream_id = get_chat_manager().get_stream_id(platform, str(id_str), is_group=is_group)
            return stream_id or ""

        except Exception:
            return ""
