"""
总控池决策器：策略解析与LLM结构化决策。
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from maibot_sdk.compat.apis import llm_api
from maibot_sdk.compat.apis.llm_api import get_available_models

try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

from ..models.global_pool import PoolCandidate

logger = get_logger(__name__)


class GlobalPoolDecider:
    """总控池决策器"""

    _DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
        "conservative": {
            "min_decision_score": 0.85,
            "trigger_probability": 0.25,
            "min_novelty_score": 0.60,
            "min_interest_score": 0.60,
            "max_candidates_per_tick": 2,
        },
        "balanced": {
            "min_decision_score": 0.75,
            "trigger_probability": 0.50,
            "min_novelty_score": 0.50,
            "min_interest_score": 0.50,
            "max_candidates_per_tick": 3,
        },
        "aggressive": {
            "min_decision_score": 0.65,
            "trigger_probability": 0.80,
            "min_novelty_score": 0.40,
            "min_interest_score": 0.40,
            "max_candidates_per_tick": 5,
        },
    }

    def __init__(self, get_config):
        self._get_config = get_config

    def resolve_policy_profile(self, stream_id: str) -> Tuple[str, Dict[str, Any]]:
        """按流解析策略配置。"""
        mapping = self._get_config("global_pool.stream_policy", {})
        if not isinstance(mapping, dict):
            mapping = {}

        default_profile = str(self._get_config("global_pool.default_policy_profile", "conservative") or "conservative")
        selected_profile = str(mapping.get(stream_id, default_profile) or default_profile).strip()

        raw_profiles = self._get_config("global_pool.policy_profiles", {})
        if not isinstance(raw_profiles, dict):
            raw_profiles = {}

        if selected_profile not in self._DEFAULT_PROFILES:
            selected_profile = "conservative"

        final_profile = dict(self._DEFAULT_PROFILES[selected_profile])
        custom = raw_profiles.get(selected_profile, {})
        if isinstance(custom, dict):
            for key in final_profile.keys():
                if key in custom:
                    final_profile[key] = custom[key]
        return selected_profile, final_profile

    def get_blocked_keywords(self) -> List[str]:
        blocked = self._get_config("global_pool.blocked_keywords", [])
        if not isinstance(blocked, list):
            return []
        return [str(item).strip().lower() for item in blocked if str(item).strip()]

    async def decide(
        self,
        candidates: List[PoolCandidate],
        whitelist_streams: List[str],
    ) -> Dict[str, Any]:
        """
        基于候选话题做结构化决策。
        返回固定结构：
        {
          should_send, target_stream_id, topic_title, topic_desc, opener, score, reason
        }
        """
        if not candidates:
            return {
                "should_send": False,
                "target_stream_id": "",
                "topic_title": "",
                "topic_desc": "",
                "opener": "",
                "score": 0.0,
                "reason": "no_candidates",
            }

        model_output = await self._llm_decide(candidates, whitelist_streams)
        if model_output:
            return model_output

        # 兜底规则：选择最高分候选
        top = sorted(candidates, key=lambda item: item.final_score, reverse=True)[0]
        return {
            "should_send": True,
            "target_stream_id": top.stream_id,
            "topic_title": top.title,
            "topic_desc": top.description,
            "opener": top.opener,
            "score": float(top.final_score),
            "reason": "rule_fallback_top_candidate",
        }

    async def _llm_decide(
        self,
        candidates: List[PoolCandidate],
        whitelist_streams: List[str],
    ) -> Optional[Dict[str, Any]]:
        try:
            model_name = str(self._get_config("llm.model_name", "utils"))
            available_models = get_available_models()
            model_config = available_models.get(model_name)
            if not model_config and available_models:
                model_config = next(iter(available_models.values()))
            if not model_config:
                return None

            candidate_lines = []
            for idx, item in enumerate(candidates[:10], 1):
                candidate_lines.append(
                    f"{idx}. stream={item.stream_id}, keyword={item.keyword}, title={item.title}, "
                    f"interest={item.interest_score:.2f}, novelty={item.novelty_score:.2f}, "
                    f"cross={item.cross_stream_score:.2f}, final={item.final_score:.2f}"
                )

            prompt = f"""
你是A_Mind总控池决策器。请基于候选话题进行一次是否主动发起的决定。

硬约束：
1. target_stream_id 必须在白名单中
2. 输出必须是JSON且字段固定
3. score是0~1小数

白名单流：
{", ".join(whitelist_streams)}

候选列表：
{chr(10).join(candidate_lines)}

请只输出JSON：
{{
  "should_send": true/false,
  "target_stream_id": "string",
  "topic_title": "string",
  "topic_desc": "string",
  "opener": "string",
  "score": 0.0,
  "reason": "string"
}}
"""

            ok, response, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=model_config,
                request_type="amind.global_pool.decide",
                temperature=0.3,
                max_tokens=400,
            )
            if not ok or not response:
                return None

            parsed = self._parse_json_block(response)
            if not parsed:
                return None

            decision = {
                "should_send": bool(parsed.get("should_send", False)),
                "target_stream_id": str(parsed.get("target_stream_id", "")).strip(),
                "topic_title": str(parsed.get("topic_title", "")).strip(),
                "topic_desc": str(parsed.get("topic_desc", "")).strip(),
                "opener": str(parsed.get("opener", "")).strip(),
                "score": float(parsed.get("score", 0.0)),
                "reason": str(parsed.get("reason", "llm_decision")).strip() or "llm_decision",
            }

            if decision["target_stream_id"] not in whitelist_streams:
                decision["should_send"] = False
                decision["reason"] = "target_stream_not_whitelisted"
            decision["score"] = max(0.0, min(1.0, decision["score"]))
            return decision

        except Exception as e:
            logger.warning(f"[A_Mind] 全局池LLM决策失败，使用规则回退: {e}")
            return None

    def _parse_json_block(self, text: str) -> Optional[Dict[str, Any]]:
        clean = str(text or "").strip()
        if not clean:
            return None
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            clean = clean[start : end + 1]

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
        return None
