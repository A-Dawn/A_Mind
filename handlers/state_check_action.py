"""
主动状态检查Action
"""
import time
from typing import List, Dict, Any, Tuple, Optional

from maibot_sdk.compat import BaseAction, ActionActivationType
from maibot_sdk.compat.apis import llm_api

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
from maibot_sdk.compat.apis.llm_api import get_available_models
try:
    from ..utils import get_global_db_manager
    from ..models.topic import Topic
except ImportError:
    # 直接导入时的备用方案
    import sys
    from pathlib import Path
    # 添加插件路径到sys.path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from utils import get_global_db_manager
    from models.topic import Topic

logger = get_logger(__name__)


class StateCheckAction(BaseAction):
    """主动状态检查Action"""

    action_name = "amind_state_check"
    action_description = "定期评估话题状态和进展"
    activation_type = ActionActivationType.ALWAYS
    action_parameters = {}
    action_require = ["定时触发", "达到回复数量阈值时触发", "管理员手动触发"]
    associated_types = ["system"]

    async def execute(self) -> Tuple[bool, str]:
        """执行状态检查"""
        try:
            check_type = self.action_data.get("check_type", "scheduled")

            # 获取需要检查的话题
            topics_to_check = self._get_topics_for_check(check_type)

            if not topics_to_check:
                return False, f"无需要{check_type}检查的话题"

            checked_count = 0
            actions_taken = []

            for topic in topics_to_check:
                try:
                    # 执行状态评估
                    assessment = await self._assess_topic_state(topic)

                    # 记录状态检查
                    self._record_state_check(topic.id, check_type, assessment)

                    # 执行自动调整
                    action = await self._execute_auto_adjustment(topic, assessment)
                    if action:
                        actions_taken.append(action)

                    checked_count += 1

                except Exception as e:
                    logger.error(f"话题 {topic.id} 状态检查失败: {e}")
                    continue

            return True, f"状态检查完成: 检查了{checked_count}个话题，执行了{len(actions_taken)}个调整动作"

        except Exception as e:
            logger.error(f"状态检查执行失败: {e}")
            return False, f"状态检查出错: {str(e)}"

    def _get_topics_for_check(self, check_type: str) -> List[Topic]:
        """获取需要检查的话题"""
        try:
            current_time = time.time()

            if check_type == "manual":
                # 手动触发：检查所有活跃话题
                return get_global_db_manager().list_topics("active")

            elif check_type == "scheduled":
                # 定时检查：检查超过间隔时间的活跃话题
                check_interval = self.get_config("state_check.check_interval_minutes", 30) * 60
                active_topics = get_global_db_manager().list_topics("active")

                topics_to_check = []
                for topic in active_topics:
                    if not topic.last_check_at or (current_time - topic.last_check_at) >= check_interval:
                        topics_to_check.append(topic)

                return topics_to_check

            elif check_type == "event":
                # 事件触发：检查达到回复阈值的活跃话题
                min_replies = self.get_config("state_check.min_replies_for_check", 5)
                active_topics = get_global_db_manager().list_topics("active")

                topics_to_check = []
                for topic in active_topics:
                    if topic.reply_count >= min_replies:
                        # 检查是否最近刚检查过（避免频繁检查）
                        if not topic.last_check_at or (current_time - topic.last_check_at) >= 300:  # 5分钟冷却
                            topics_to_check.append(topic)

                return topics_to_check

            else:
                return []

        except Exception as e:
            logger.error(f"获取检查话题失败: {e}")
            return []

    async def _assess_topic_state(self, topic: Topic) -> Dict[str, Any]:
        """使用LLM评估话题状态"""
        try:
            # 获取话题的最近活动数据
            recent_replies = get_global_db_manager().get_recent_replies(topic.id, 20)

            # 简化评估逻辑
            current_time = time.time()
            hours_since_activity = (current_time - topic.last_activity) / 3600 if topic.last_activity else 24
            days_since_creation = (current_time - topic.created_at) / 86400

            # 基于规则的简单评估
            if topic.reply_count == 0:
                engagement = 0.0
            elif hours_since_activity < 1:
                engagement = 0.9
            elif hours_since_activity < 24:
                engagement = 0.7
            else:
                engagement = 0.3

            # 进展评估
            if days_since_creation < 1:
                progress = 0.2  # 新话题
            elif topic.reply_count > 10:
                progress = 0.8  # 活跃话题
            elif topic.reply_count > 5:
                progress = 0.6  # 中等活跃
            else:
                progress = 0.4  # 低活跃

            # 情感评估（简化）
            sentiment = 0.5

            # 推荐行动
            if engagement > 0.7 and progress > 0.6:
                recommendation = "continue"
                reason = "话题进展良好，继续保持"
            elif engagement > 0.4:
                recommendation = "continue"
                reason = "话题进展正常"
            elif hours_since_activity > 24 and engagement > 0.5:
                recommendation = "initiate"
                reason = "话题进展良好但需要引导继续讨论"
            else:
                recommendation = "pause"
                reason = "话题活跃度不足，建议暂停"

            return {
                "engagement_score": engagement,
                "progress_score": progress,
                "sentiment_score": sentiment,
                "recommendation": recommendation,
                "reason": reason,
            }

        except Exception as e:
            logger.error(f"话题状态评估失败: {e}")
            return {
                "engagement_score": 0.5,
                "progress_score": 0.5,
                "sentiment_score": 0.5,
                "recommendation": "continue",
                "reason": "评估失败，使用默认值",
            }

    def _record_state_check(self, topic_id: int, check_type: str, assessment: Dict[str, Any]):
        """记录状态检查结果"""
        try:
            check_record = {
                "topic_id": topic_id,
                "check_type": check_type,
                "engagement_score": assessment.get("engagement_score", 0.0),
                "sentiment_score": assessment.get("sentiment_score", 0.5),
                "progress_score": assessment.get("progress_score", 0.5),
                "recommendation": assessment.get("recommendation", "continue"),
                "action_taken": "",
                "created_at": time.time(),
            }

            get_global_db_manager().add_state_check_record(check_record)

            # 更新话题的检查统计
            updates = {
                "check_count": 0,  # 将由数据库管理器处理
                "last_check_at": time.time(),
            }

        except Exception as e:
            logger.error(f"记录状态检查失败: {e}")

    async def _execute_auto_adjustment(self, topic: Topic, assessment: Dict[str, Any]) -> Optional[str]:
        """执行自动状态调整"""
        try:
            recommendation = assessment.get("recommendation", "continue")

            actions_taken = []

            if recommendation == "continue":
                # 继续话题：更新参与度分数
                updates = {"engagement_score": assessment.get("engagement_score", topic.engagement_score)}
                get_global_db_manager().update_topic(topic.id, updates)

            elif recommendation == "pause":
                # 暂停话题
                updates = {"status": "paused"}
                get_global_db_manager().update_topic(topic.id, updates)
                actions_taken.append(f"话题 {topic.title} 已暂停")

            elif recommendation == "terminate":
                # 终止话题
                updates = {"status": "terminated"}
                get_global_db_manager().update_topic(topic.id, updates)
                actions_taken.append(f"话题 {topic.title} 已终止")

            elif recommendation == "initiate":
                # 标记需要自发起
                updates = {
                    "status": "paused",  # 暂停等待自发起
                    "engagement_score": assessment.get("engagement_score", topic.engagement_score),
                }
                get_global_db_manager().update_topic(topic.id, updates)
                actions_taken.append(f"话题 {topic.title} 标记为需要自发起")

            return "; ".join(actions_taken) if actions_taken else None

        except Exception as e:
            logger.error(f"执行自动调整失败: {e}")
            return f"调整失败: {str(e)}"
