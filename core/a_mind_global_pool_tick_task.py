"""
A_Mind 总控池 Tick 任务
"""

import asyncio
import contextlib
import random
import time
from typing import Callable, Dict, Optional

from src.manager.async_task_manager import AsyncTask

try:
    from .amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

from ..models.auto_send import AutoSendRequest
from ..models.global_pool import PoolDecision
from ..models.topic import Topic
from ..services.auto_sender import AutoSender
from ..services.global_pool_decider import GlobalPoolDecider
from ..services.global_pool_service import GlobalPoolService
from ..utils import get_global_db_manager

logger = get_logger(__name__)


class AMindGlobalPoolTickTask(AsyncTask):
    """总控池扫描与主动发起任务"""

    def __init__(self, get_config: Callable, auto_sender: Optional[AutoSender] = None, plugin_id: str = ""):
        self._get_config = get_config
        self._db = get_global_db_manager()
        self._auto_sender = auto_sender or AutoSender(self._db)
        self._service = GlobalPoolService(get_config=get_config, db_manager=self._db)
        self._decider = GlobalPoolDecider(get_config=get_config)
        self._lock = asyncio.Lock()
        self._plugin_id = str(plugin_id or "")
        super().__init__(
            task_name="A_MindGlobalPoolTickTask",
            wait_before_start=0,
            run_interval=int(get_config("global_pool.tick_interval_seconds", 300)),
        )

    async def run(self):
        with self._plugin_context():
            await self._run_inner()

    async def _run_inner(self):
        if not self._service.is_enabled():
            return
        if self._is_dnd_active():
            return

        whitelist = self._service.get_whitelist_streams()
        if not whitelist:
            return

        try:
            await self._auto_sender.process_queue()
        except Exception as e:
            logger.error(f"[A_Mind][GlobalPool] AutoSender处理失败: {e}")

        async with self._lock:
            try:
                self._service.cleanup_expired()
                lookback_hours = int(self._get_config("global_pool.lookback_hours", 12))
                min_messages = int(self._get_config("global_pool.min_messages_for_analysis", 20))
                enable_cross = bool(self._get_config("global_pool.enable_cross_stream_boost", True))

                candidates, diagnostics = self._service.build_candidates_for_whitelist(
                    whitelist_streams=whitelist,
                    lookback_hours=lookback_hours,
                    min_messages=min_messages,
                    max_candidates_per_stream=5,
                    enable_cross_stream_boost=enable_cross,
                )
                if not candidates:
                    return
                logger.debug(f"[A_Mind][GlobalPool] 候选构建完成: {diagnostics}")

                # 按流应用 profile 的候选上限
                limited_candidates = []
                for stream_id in whitelist:
                    _, profile = self._decider.resolve_policy_profile(stream_id)
                    stream_candidates = [item for item in candidates if item.stream_id == stream_id]
                    stream_candidates.sort(key=lambda item: item.final_score, reverse=True)
                    cap = max(1, int(profile.get("max_candidates_per_tick", 2)))
                    limited_candidates.extend(stream_candidates[:cap])
                candidates = sorted(limited_candidates, key=lambda item: item.final_score, reverse=True)

                decision = await self._decider.decide(candidates, whitelist)
                chosen = self._pick_candidate(candidates, decision)
                if not chosen:
                    self._record_decision(
                        stream_id=str(decision.get("target_stream_id", "") or ""),
                        policy_profile="conservative",
                        decision=decision,
                        selected_topic_title="",
                        score=float(decision.get("score", 0.0) or 0.0),
                        sent=False,
                        reason="candidate_not_found",
                    )
                    return

                profile_name, profile = self._decider.resolve_policy_profile(chosen.stream_id)
                guard_ok, guard_reason = self._apply_guardrails(
                    decision=decision,
                    chosen_candidate=chosen,
                    profile_name=profile_name,
                    profile=profile,
                )

                if not guard_ok:
                    self._record_decision(
                        stream_id=chosen.stream_id,
                        policy_profile=profile_name,
                        decision=decision,
                        selected_topic_title=decision.get("topic_title", "") or chosen.title,
                        score=float(decision.get("score", 0.0) or 0.0),
                        sent=False,
                        reason=guard_reason,
                    )
                    return

                sent_ok, send_reason = await self._send_decision(chosen.stream_id, decision, chosen, profile_name)
                self._record_decision(
                    stream_id=chosen.stream_id,
                    policy_profile=profile_name,
                    decision=decision,
                    selected_topic_title=decision.get("topic_title", "") or chosen.title,
                    score=float(decision.get("score", 0.0) or 0.0),
                    sent=sent_ok,
                    reason=send_reason,
                )
                if sent_ok:
                    logger.info(
                        f"[A_Mind][GlobalPool] 已主动发起: stream={chosen.stream_id}, "
                        f"title={decision.get('topic_title', chosen.title)}"
                    )
            except Exception as e:
                logger.error(f"[A_Mind][GlobalPool] Tick执行异常: {e}")

    def _pick_candidate(self, candidates, decision: Dict) -> Optional[object]:
        target_stream = str(decision.get("target_stream_id", "")).strip()
        target_title = str(decision.get("topic_title", "")).strip().lower()
        if target_stream:
            for item in candidates:
                if item.stream_id != target_stream:
                    continue
                if target_title and target_title in item.title.lower():
                    return item
            for item in candidates:
                if item.stream_id == target_stream:
                    return item
        return candidates[0] if candidates else None

    def _apply_guardrails(self, decision: Dict, chosen_candidate, profile_name: str, profile: Dict) -> tuple[bool, str]:
        if not bool(decision.get("should_send", False)):
            return False, "llm_declined"

        score = float(decision.get("score", 0.0) or 0.0)
        if score < float(profile.get("min_decision_score", 0.85)):
            return False, "below_min_decision_score"

        if chosen_candidate.novelty_score < float(profile.get("min_novelty_score", 0.6)):
            return False, "below_min_novelty_score"

        if chosen_candidate.interest_score < float(profile.get("min_interest_score", 0.6)):
            return False, "below_min_interest_score"

        trigger_probability = float(profile.get("trigger_probability", 0.25))
        if random.random() > trigger_probability:
            return False, "trigger_probability_not_met"

        blocked_keywords = self._decider.get_blocked_keywords()
        text_for_block = (
            f"{decision.get('topic_title', '')} {decision.get('topic_desc', '')} {decision.get('opener', '')}"
        ).lower()
        if blocked_keywords and any(keyword in text_for_block for keyword in blocked_keywords):
            return False, "blocked_keyword"

        now = time.time()
        global_cd = int(self._get_config("global_pool.global_cooldown_seconds", 1800))
        stream_cd = int(self._get_config("global_pool.per_stream_cooldown_seconds", 7200))

        last_global = self._db.get_last_pool_decision_time(stream_id=None, sent_only=True)
        if last_global and (now - last_global) < global_cd:
            return False, "global_cooldown"

        last_stream = self._db.get_last_pool_decision_time(stream_id=chosen_candidate.stream_id, sent_only=True)
        if last_stream and (now - last_stream) < stream_cd:
            return False, "stream_cooldown"

        day_start = now - (now % 86400)
        global_day_count = self._db.count_pool_decisions_since(day_start, stream_id=None, sent_only=True)
        if global_day_count >= int(self._get_config("global_pool.max_global_sends_per_day", 6)):
            return False, "global_daily_limit"

        stream_day_count = self._db.count_pool_decisions_since(
            day_start,
            stream_id=chosen_candidate.stream_id,
            sent_only=True,
        )
        if stream_day_count >= int(self._get_config("global_pool.max_per_stream_sends_per_day", 2)):
            return False, "stream_daily_limit"

        return True, "ok"

    async def _send_decision(self, stream_id: str, decision: Dict, chosen_candidate, profile_name: str) -> tuple[bool, str]:
        title = str(decision.get("topic_title", "")).strip() or chosen_candidate.title
        description = str(decision.get("topic_desc", "")).strip() or chosen_candidate.description
        opener = str(decision.get("opener", "")).strip() or chosen_candidate.opener

        topic = Topic(
            title=title,
            description=description,
            creator_id="a_mind_global_pool",
            creator_name="A_Mind_GlobalPool",
            status="active",
            priority=2,
            visibility="public",
            stream_ids=[stream_id],
            created_at=time.time(),
            updated_at=time.time(),
            last_activity=time.time(),
            config={
                "source": "global_pool",
                "policy_profile": profile_name,
                "keyword": chosen_candidate.keyword,
            },
        )
        topic_id = self._db.create_topic(topic)
        if not topic_id:
            return False, "create_topic_failed"

        content = f"{opener}\n\n（话题：{title}）"
        send_request = AutoSendRequest(
            topic_id=topic_id,
            content=content,
            send_type="initiate",
            priority=4,
            scheduled_time=time.time(),
            stream_id=stream_id,
            conditions={"min_engagement": 0.0, "min_interval_hours": 0, "max_sends_per_day": 99},
        )

        send_ok = await self._auto_sender.schedule_send(send_request)
        return (True, "sent") if send_ok else (False, "send_failed")

    def _record_decision(
        self,
        stream_id: str,
        policy_profile: str,
        decision: Dict,
        selected_topic_title: str,
        score: float,
        sent: bool,
        reason: str,
    ):
        self._db.add_pool_decision(
            PoolDecision(
                stream_id=stream_id,
                policy_profile=policy_profile,
                decision=decision,
                selected_topic_title=selected_topic_title,
                score=score,
                sent=sent,
                reason=reason,
                created_at=time.time(),
            )
        )

    def _is_dnd_active(self) -> bool:
        """检查当前是否处于免打扰时段"""
        try:
            enabled = self._get_config("topic_management.dnd_enabled", False)
            if not enabled:
                return False

            start_str = str(self._get_config("topic_management.dnd_start_time", "23:00"))
            end_str = str(self._get_config("topic_management.dnd_end_time", "08:00"))

            current_time = time.localtime()
            current_val = current_time.tm_hour * 60 + current_time.tm_min

            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start_val = sh * 60 + sm
            end_val = eh * 60 + em

            if start_val < end_val:
                return start_val <= current_val < end_val
            return current_val >= start_val or current_val < end_val
        except Exception as e:
            logger.error(f"[A_Mind][GlobalPool] DND检查失败: {e}")
            return False

    @contextlib.contextmanager
    def _plugin_context(self):
        token = None
        try:
            if self._plugin_id:
                from maibot_sdk.compat import _context_holder

                token = _context_holder.activate_plugin(self._plugin_id)
            yield
        finally:
            if token is not None:
                with contextlib.suppress(Exception):
                    from maibot_sdk.compat import _context_holder

                    _context_holder.deactivate_plugin(token)
