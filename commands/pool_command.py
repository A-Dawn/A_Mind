"""
总控池管理命令
"""

import re
import time
from typing import Tuple

from src.plugin_system import BaseCommand, ComponentInfo, ComponentType, CommandInfo

from ..core.permissions import require_permission
from ..services.global_pool_decider import GlobalPoolDecider
from ..services.global_pool_service import GlobalPoolService
from ..utils import get_global_db_manager

try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

logger = get_logger(__name__)


class PoolCommand(BaseCommand):
    """总控池命令"""

    command_name = "amind_pool"
    command_description = "查看总控池状态和干运行结果"
    command_pattern = r"^/amind_pool(?:\s+(status|dryrun|whitelist|profile))?$"

    @require_permission("admin")
    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            message_text = getattr(self.message, "plain_text", getattr(self.message, "processed_plain_text", ""))
            match = re.match(self.command_pattern, message_text.strip())
            if not match:
                return False, "命令格式错误，使用 /amind_pool [status|dryrun|whitelist|profile]", False

            action = (match.group(1) or "status").lower()
            service = GlobalPoolService(self.get_config, db_manager=get_global_db_manager())
            decider = GlobalPoolDecider(self.get_config)
            whitelist = service.get_whitelist_streams()

            if action == "whitelist":
                text = "📌 总控池白名单流\n"
                if whitelist:
                    for idx, stream_id in enumerate(whitelist, 1):
                        text += f"{idx}. {stream_id}\n"
                else:
                    text += "（空）\n"
                await self.send_text(text)
                return True, "show_whitelist", True

            if action == "profile":
                text = "🎛️ 总控池策略映射\n"
                if not whitelist:
                    text += "白名单为空\n"
                for stream_id in whitelist:
                    profile_name, profile = decider.resolve_policy_profile(stream_id)
                    text += (
                        f"- {stream_id}: {profile_name} "
                        f"(score>={profile.get('min_decision_score')}, "
                        f"prob={profile.get('trigger_probability')})\n"
                    )
                await self.send_text(text)
                return True, "show_profile", True

            if action == "dryrun":
                if not self.get_config("global_pool.enabled", False):
                    await self.send_text("总控池未启用（global_pool.enabled=false）")
                    return True, "dryrun_disabled", True
                if not whitelist:
                    await self.send_text("总控池白名单为空，请先配置 global_pool.whitelist_streams")
                    return True, "dryrun_empty_whitelist", True

                lookback_hours = int(self.get_config("global_pool.lookback_hours", 12))
                min_messages = int(self.get_config("global_pool.min_messages_for_analysis", 20))
                enable_cross = bool(self.get_config("global_pool.enable_cross_stream_boost", True))
                candidates, diagnostics = service.build_candidates_for_whitelist(
                    whitelist_streams=whitelist,
                    lookback_hours=lookback_hours,
                    min_messages=min_messages,
                    max_candidates_per_stream=5,
                    enable_cross_stream_boost=enable_cross,
                )
                if not candidates:
                    await self.send_text(
                        "DryRun结果：暂无可用候选\n"
                        f"统计：{diagnostics.get('streams', {})}"
                    )
                    return True, "dryrun_no_candidates", True

                decision = await decider.decide(candidates, whitelist)
                top = candidates[:3]
                lines = ["🧪 总控池 DryRun", "Top候选："]
                for idx, item in enumerate(top, 1):
                    lines.append(
                        f"{idx}. [{item.stream_id}] {item.title} "
                        f"(final={item.final_score:.2f}, interest={item.interest_score:.2f}, novelty={item.novelty_score:.2f})"
                    )
                lines.append("")
                lines.append(
                    "建议决策："
                    f"should_send={decision.get('should_send')}, "
                    f"target={decision.get('target_stream_id')}, "
                    f"score={float(decision.get('score', 0.0)):.2f}, "
                    f"reason={decision.get('reason')}"
                )
                await self.send_text("\n".join(lines))
                return True, "dryrun_ok", True

            # 默认 status
            now = time.time()
            day_start = now - (now % 86400)
            db = get_global_db_manager()
            global_day_count = db.count_pool_decisions_since(day_start, sent_only=True)
            last_global_sent = db.get_last_pool_decision_time(sent_only=True)
            event_count = 0
            for stream_id in whitelist:
                event_count += len(db.list_pool_events(stream_id=stream_id, since_ts=now - 24 * 3600, limit=1000))

            status_text = "📊 总控池状态\n"
            status_text += f"- enabled: {bool(self.get_config('global_pool.enabled', False))}\n"
            status_text += f"- 白名单流数量: {len(whitelist)}\n"
            status_text += f"- 近24h事件数(白名单): {event_count}\n"
            status_text += f"- 今日已发送: {global_day_count}\n"
            status_text += (
                f"- 最近发送时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_global_sent))}\n"
                if last_global_sent
                else "- 最近发送时间: 无\n"
            )
            await self.send_text(status_text)
            return True, "show_status", True

        except Exception as e:
            logger.error(f"PoolCommand执行失败: {e}")
            return False, f"执行失败: {str(e)}", False

    @staticmethod
    def get_command_info() -> ComponentInfo:
        return CommandInfo(
            name="amind_pool",
            component_type=ComponentType.COMMAND,
            command_pattern=r"^/amind_pool(?:\s+(status|dryrun|whitelist|profile))?$",
            description="总控池状态/白名单/策略/DryRun - 用法: /amind_pool [status|dryrun|whitelist|profile]",
        )
