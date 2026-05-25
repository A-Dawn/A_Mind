"""
总控池服务：消息采集、特征提取、候选话题构建、过期清理。
"""

import hashlib
import re
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

try:
    import jieba

    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

from ..models.global_pool import PoolCandidate, PoolEvent
from ..utils import get_global_db_manager

logger = get_logger(__name__)


class GlobalPoolService:
    """总控池服务"""

    _STOP_WORDS = {
        "我们",
        "你们",
        "他们",
        "这个",
        "那个",
        "这些",
        "那些",
        "然后",
        "就是",
        "因为",
        "所以",
        "但是",
        "可以",
        "一个",
        "一下",
        "今天",
        "最近",
        "感觉",
        "真的",
        "哈哈",
        "时候",
    }

    def __init__(self, get_config, db_manager=None):
        self._get_config = get_config
        self._db = db_manager or get_global_db_manager()

    def is_enabled(self) -> bool:
        return bool(self._get_config("global_pool.enabled", False))

    def get_whitelist_streams(self) -> List[str]:
        raw = self._get_config("global_pool.whitelist_streams", [])
        if not isinstance(raw, list):
            return []
        streams = [str(item).strip() for item in raw if str(item).strip()]
        return list(dict.fromkeys(streams))

    def collect_message(
        self,
        stream_id: str,
        message_id: str,
        user_id: str,
        content: str,
        role: str = "user",
        created_at: Optional[float] = None,
    ) -> Optional[int]:
        """采集一条消息到总控池。"""
        text = self._normalize_text(content)
        if not text:
            return None

        now = created_at or time.time()
        summary_limit = 160
        raw_limit = 500
        summary_retention_hours = int(self._get_config("global_pool.summary_retention_hours", 72))
        raw_retention_hours = int(self._get_config("global_pool.raw_retention_hours", 24))

        features = self._extract_features(text)
        event = PoolEvent(
            stream_id=stream_id,
            message_id=message_id or "",
            user_id_hash=self._hash_user_id(user_id),
            role=role or "user",
            summary_text=text[:summary_limit],
            raw_text=text[:raw_limit],
            features=features,
            created_at=now,
            summary_expire_at=now + max(summary_retention_hours, 1) * 3600,
            raw_expire_at=now + max(raw_retention_hours, 1) * 3600,
        )
        return self._db.add_pool_event(event)

    def cleanup_expired(self) -> Dict[str, int]:
        return self._db.cleanup_pool_data(time.time())

    def build_candidates_for_whitelist(
        self,
        whitelist_streams: List[str],
        lookback_hours: int = 12,
        min_messages: int = 20,
        max_candidates_per_stream: int = 5,
        enable_cross_stream_boost: bool = True,
    ) -> Tuple[List[PoolCandidate], Dict[str, Any]]:
        """
        为白名单流构建候选话题。
        """
        now = time.time()
        since_ts = now - max(1, lookback_hours) * 3600

        events_by_stream: Dict[str, List[PoolEvent]] = {}
        diagnostics: Dict[str, Any] = {
            "streams": {},
            "skipped_streams": [],
            "candidate_count": 0,
        }

        for stream_id in whitelist_streams:
            events = self._db.list_pool_events(stream_id=stream_id, since_ts=since_ts, limit=1200)
            diagnostics["streams"][stream_id] = {"event_count": len(events)}
            if len(events) < min_messages:
                diagnostics["skipped_streams"].append(stream_id)
                continue
            events_by_stream[stream_id] = events

        if not events_by_stream:
            return [], diagnostics

        keyword_stream_presence: Dict[str, set] = defaultdict(set)
        stream_keyword_stats: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for stream_id, events in events_by_stream.items():
            keyword_stats: Dict[str, Dict[str, Any]] = {}
            for event in events:
                features = event.features or {}
                keywords = features.get("keywords")
                if not isinstance(keywords, list) or not keywords:
                    keywords = self._extract_keywords(event.summary_text, top_n=6)
                has_question = bool(features.get("has_question", False))
                emotion = str(features.get("emotion", "neutral"))

                for keyword in keywords[:5]:
                    if keyword not in keyword_stats:
                        keyword_stats[keyword] = {
                            "count": 0,
                            "question_count": 0,
                            "emotion_count": 0,
                            "samples": [],
                        }
                    stat = keyword_stats[keyword]
                    stat["count"] += 1
                    if has_question:
                        stat["question_count"] += 1
                    if emotion in {"positive", "negative"}:
                        stat["emotion_count"] += 1
                    if len(stat["samples"]) < 3:
                        stat["samples"].append(event.summary_text[:60])
                    keyword_stream_presence[keyword].add(stream_id)

            stream_keyword_stats[stream_id] = keyword_stats

        recent_titles_by_stream: Dict[str, List[str]] = defaultdict(list)
        recent_decisions = self._db.list_pool_decisions(
            stream_id=None,
            since_ts=since_ts - 24 * 3600,
            sent_only=True,
            limit=1000,
        )
        for decision in recent_decisions:
            recent_titles_by_stream[decision.stream_id].append(decision.selected_topic_title.lower())

        candidates: List[PoolCandidate] = []
        active_stream_count = max(len(events_by_stream), 1)

        for stream_id, keyword_stats in stream_keyword_stats.items():
            stream_candidates: List[PoolCandidate] = []
            recent_titles = recent_titles_by_stream.get(stream_id, [])
            for keyword, stat in keyword_stats.items():
                count = int(stat.get("count", 0))
                if count <= 0:
                    continue

                question_ratio = stat.get("question_count", 0) / max(count, 1)
                emotion_ratio = stat.get("emotion_count", 0) / max(count, 1)
                interest_score = min(1.0, (count / 8.0) + question_ratio * 0.2 + emotion_ratio * 0.1)

                repeat_hits = sum(1 for title in recent_titles if keyword.lower() in title)
                novelty_score = max(0.05, 1.0 - repeat_hits * 0.3)
                repeat_penalty = min(0.4, repeat_hits * 0.12)

                stream_presence = len(keyword_stream_presence.get(keyword, set()))
                cross_stream_score = 0.0
                if enable_cross_stream_boost and active_stream_count > 1:
                    cross_stream_score = max(0.0, (stream_presence - 1) / (active_stream_count - 1))

                final_score = (
                    interest_score * 0.55
                    + novelty_score * 0.35
                    + cross_stream_score * (0.10 if enable_cross_stream_boost else 0.0)
                    - repeat_penalty
                )
                final_score = max(0.0, min(1.0, final_score))

                samples = stat.get("samples", [])
                sample_text = "；".join(samples[:2]) if samples else "大家聊得很热闹。"
                title = f"最近大家在聊「{keyword}」"
                description = f"观察到多个消息围绕“{keyword}”展开：{sample_text}"
                opener = f"看到大家最近经常提到「{keyword}」，你更关注它的哪一面？"

                stream_candidates.append(
                    PoolCandidate(
                        stream_id=stream_id,
                        keyword=keyword,
                        title=title[:60],
                        description=description[:200],
                        opener=opener[:120],
                        interest_score=round(interest_score, 4),
                        novelty_score=round(novelty_score, 4),
                        cross_stream_score=round(cross_stream_score, 4),
                        repeat_penalty=round(repeat_penalty, 4),
                        final_score=round(final_score, 4),
                        source_samples=samples,
                    )
                )

            stream_candidates.sort(key=lambda item: item.final_score, reverse=True)
            candidates.extend(stream_candidates[: max(1, max_candidates_per_stream)])

        candidates.sort(key=lambda item: item.final_score, reverse=True)
        diagnostics["candidate_count"] = len(candidates)
        return candidates, diagnostics

    def _hash_user_id(self, user_id: str) -> str:
        source = str(user_id or "anonymous")
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return digest[:16]

    def _normalize_text(self, text: str) -> str:
        text = str(text or "")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_features(self, text: str) -> Dict[str, Any]:
        keywords = self._extract_keywords(text, top_n=8)
        has_question = bool(re.search(r"[?？]|(吗$)|(^问一下)", text))
        emotion = self._classify_emotion(text)
        return {
            "keywords": keywords,
            "has_question": has_question,
            "emotion": emotion,
            "length": len(text),
        }

    def _extract_keywords(self, text: str, top_n: int = 8) -> List[str]:
        if not text:
            return []

        tokens: List[str] = []
        if JIEBA_AVAILABLE:
            tokens = [word.strip().lower() for word in jieba.cut(text) if word and word.strip()]
        else:
            tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_]{2,}", text.lower())

        cleaned = []
        for token in tokens:
            token = token.strip()
            if len(token) < 2:
                continue
            if token in self._STOP_WORDS:
                continue
            if token.isdigit():
                continue
            cleaned.append(token)

        if not cleaned:
            return []
        counter = Counter(cleaned)
        return [word for word, _ in counter.most_common(top_n)]

    def _classify_emotion(self, text: str) -> str:
        positive_words = ["开心", "高兴", "喜欢", "赞", "厉害", "太棒", "激动", "幸福"]
        negative_words = ["难过", "生气", "烦", "郁闷", "糟糕", "崩溃", "失望", "焦虑"]

        pos = sum(1 for word in positive_words if word in text)
        neg = sum(1 for word in negative_words if word in text)
        if pos > neg:
            return "positive"
        if neg > pos:
            return "negative"
        return "neutral"
