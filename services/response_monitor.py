"""
响应监测器 - 监测自发起后的用户参与度
"""

import time
from typing import Dict, Any, Optional, List

try:
    from ..models.metrics import EngagementMetrics, MonitoringResult
    from ..database import get_db_connection
except ImportError:
    # 直接导入时使用绝对导入
    from plugins.A_Mind.models.metrics import EngagementMetrics, MonitoringResult
    from plugins.A_Mind.database import get_db_connection
from src.common.logger import get_logger

logger = get_logger("A_mind")


class ResponseMonitor:
    """响应监测器 - 监测自发起后的用户参与度"""

    def __init__(self):
        self.monitoring_topics = {}  # topic_id -> monitoring_start_time

    async def start_monitoring(self, topic_id: int, monitoring_window_hours: int = 24) -> bool:
        """开始监测话题响应"""
        try:
            if topic_id in self.monitoring_topics:
                logger.info(f"[A_mind] 话题 {topic_id} 已在监测中")
                return True

            # 记录监测开始时间
            self.monitoring_topics[topic_id] = {
                "start_time": time.time(),
                "window_hours": monitoring_window_hours,
                "baseline_metrics": await self._get_baseline_metrics(topic_id),
            }

            logger.info(f"[A_mind] 开始监测话题 {topic_id} 响应，监测窗口: {monitoring_window_hours}小时")
            return True

        except Exception as e:
            logger.error(f"开始响应监测失败: {e}")
            return False

    async def stop_monitoring(self, topic_id: int) -> Optional[MonitoringResult]:
        """停止监测并返回结果"""
        try:
            if topic_id not in self.monitoring_topics:
                logger.warning(f"[A_mind] 话题 {topic_id} 不在监测列表中")
                return None

            monitoring_data = self.monitoring_topics.pop(topic_id)

            # 计算最终监测结果
            result = await self._calculate_monitoring_result(topic_id, monitoring_data)

            logger.info(f"[A_mind] 停止监测话题 {topic_id}, 成功度: {result.success_score:.2f}")
            return result

        except Exception as e:
            logger.error(f"停止响应监测失败: {e}")
            return None

    async def check_monitoring_status(self, topic_id: int) -> Optional[Dict[str, Any]]:
        """检查监测状态"""
        try:
            if topic_id not in self.monitoring_topics:
                return None

            monitoring_data = self.monitoring_topics[topic_id]
            elapsed_hours = (time.time() - monitoring_data["start_time"]) / 3600
            window_hours = monitoring_data["window_hours"]

            # 获取当前指标
            current_metrics = await self._measure_engagement(topic_id, monitoring_data["start_time"])

            status = {
                "topic_id": topic_id,
                "elapsed_hours": elapsed_hours,
                "remaining_hours": max(0, window_hours - elapsed_hours),
                "progress_percentage": min(100, (elapsed_hours / window_hours) * 100),
                "current_metrics": current_metrics,
                "baseline_metrics": monitoring_data["baseline_metrics"],
                "is_complete": elapsed_hours >= window_hours,
            }

            return status

        except Exception as e:
            logger.error(f"检查监测状态失败: {e}")
            return None

    async def _get_baseline_metrics(self, topic_id: int) -> EngagementMetrics:
        """获取基线参与度指标"""
        try:
            # 获取自发起前1小时的数据作为基线
            baseline_end = time.time()
            baseline_start = baseline_end - 3600  # 1小时前

            return await self._measure_engagement(topic_id, baseline_start, baseline_end)

        except Exception as e:
            logger.error(f"获取基线指标失败: {e}")
            return EngagementMetrics()

    async def _measure_engagement(
        self, topic_id: int, start_time: float, end_time: Optional[float] = None
    ) -> EngagementMetrics:
        """测量参与度指标"""
        try:
            if end_time is None:
                end_time = time.time()

            # 获取时间窗口内的回复
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM amind_replies
                WHERE topic_id = ? AND created_at BETWEEN ? AND ?
                ORDER BY created_at ASC
            """,
                (topic_id, start_time, end_time),
            )

            replies = cursor.fetchall()

            if not replies:
                return EngagementMetrics(
                    reply_count=0, unique_users=0, sentiment_score=0.5, sustained_attention=0.0, conversation_depth=0.0
                )

            # 计算基础指标
            reply_count = len(replies)
            unique_users = len(set(reply["user_id"] for reply in replies))

            # 计算平均响应时间
            response_times = []
            for i in range(1, len(replies)):
                time_diff = replies[i]["created_at"] - replies[i - 1]["created_at"]
                response_times.append(time_diff)

            avg_response_time = sum(response_times) / len(response_times) if response_times else 0

            # 计算情感得分（简化版）
            sentiment_score = await self._calculate_sentiment_score(replies)

            # 计算持续关注度（基于回复分布）
            sustained_attention = self._calculate_sustained_attention(replies, start_time, end_time)

            # 计算对话深度（基于回复长度和复杂度）
            conversation_depth = self._calculate_conversation_depth(replies)

            return EngagementMetrics(
                reply_count=reply_count,
                unique_users=unique_users,
                avg_response_time=avg_response_time,
                sentiment_score=sentiment_score,
                sustained_attention=sustained_attention,
                conversation_depth=conversation_depth,
            )

        except Exception as e:
            logger.error(f"测量参与度失败: {e}")
            return EngagementMetrics()

    async def _calculate_sentiment_score(self, replies: List) -> float:
        """计算情感得分"""
        try:
            # 简化版情感分析（基于关键词）
            positive_words = ["好", "不错", "棒", "支持", "同意", "喜欢", "有趣", "精彩"]
            negative_words = ["不好", "差", "反对", "不喜欢", "无聊", "糟糕", "无趣"]

            total_score = 0
            for reply in replies:
                # sqlite3.Row对象通过列名访问，不支持.get()方法
                content = str(reply["message_content"]).lower() if "message_content" in reply else ""
                positive_count = sum(1 for word in positive_words if word in content)
                negative_count = sum(1 for word in negative_words if word in content)

                # 计算这条回复的情感得分
                if positive_count + negative_count > 0:
                    score = (positive_count - negative_count) / (positive_count + negative_count)
                    score = (score + 1) / 2  # 转换为0-1范围
                else:
                    score = 0.5  # 中性

                total_score += score

            return total_score / len(replies) if replies else 0.5

        except Exception as e:
            logger.warning(f"情感得分计算失败: {e}")
            return 0.5

    def _calculate_sustained_attention(self, replies: List[Dict[str, Any]], start_time: float, end_time: float) -> float:
        """计算持续关注度"""
        try:
            if not replies:
                return 0.0

            window_duration = end_time - start_time

            # 计算回复的时间分布
            reply_times = [reply["created_at"] for reply in replies]
            reply_times.sort()

            # 计算回复间隔的标准差（标准差越小，分布越均匀，关注度越高）
            if len(reply_times) > 1:
                intervals = []
                for i in range(1, len(reply_times)):
                    intervals.append(reply_times[i] - reply_times[i - 1])

                if intervals:
                    mean_interval = sum(intervals) / len(intervals)
                    variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
                    std_dev = variance**0.5

                    # 标准差占窗口时间的比例，越小越好
                    normalized_std = std_dev / window_duration
                    sustained_attention = max(0, 1 - normalized_std * 10)  # 归一化到0-1
                else:
                    sustained_attention = 0.5
            else:
                sustained_attention = 0.5  # 只有一个回复，中等关注度

            return sustained_attention

        except Exception as e:
            logger.warning(f"持续关注度计算失败: {e}")
            return 0.5

    def _calculate_conversation_depth(self, replies: List) -> float:
        """计算对话深度"""
        try:
            if not replies:
                return 0.0

            # 基于回复长度的对话深度
            total_length = sum(
                len(str(reply["message_content"])) if "message_content" in reply else 0 for reply in replies
            )
            avg_length = total_length / len(replies)

            # 基于用户多样性的对话深度
            unique_users = len(set(reply["user_id"] for reply in replies))
            user_diversity = unique_users / len(replies)

            # 综合评分
            length_score = min(avg_length / 100, 1.0)  # 平均100字符为满分
            diversity_score = user_diversity

            return length_score * 0.6 + diversity_score * 0.4

        except Exception as e:
            logger.warning(f"对话深度计算失败: {e}")
            return 0.5

    async def _calculate_monitoring_result(self, topic_id: int, monitoring_data: Dict[str, Any]) -> MonitoringResult:
        """计算监测结果"""
        try:
            start_time = monitoring_data["start_time"]
            baseline_metrics = monitoring_data["baseline_metrics"]

            # 获取最终指标
            final_metrics = await self._measure_engagement(topic_id, start_time)

            # 计算成功度
            success_score = self._calculate_success_score(baseline_metrics, final_metrics)

            # 分析参与趋势
            engagement_trend = self._analyze_engagement_trend(baseline_metrics, final_metrics)

            # 生成建议
            recommendations = self._generate_recommendations(success_score, engagement_trend, final_metrics)

            # 决定下一步行动
            next_action = self._decide_next_action(success_score, engagement_trend, final_metrics)

            return MonitoringResult(
                topic_id=topic_id,
                success_score=success_score,
                engagement_trend=engagement_trend,
                recommendations=recommendations,
                next_action=next_action,
            )

        except Exception as e:
            logger.error(f"计算监测结果失败: {e}")
            return MonitoringResult(topic_id=topic_id, success_score=0.0)

    def _calculate_success_score(self, baseline: EngagementMetrics, final: EngagementMetrics) -> float:
        """计算成功度评分"""
        try:
            # 基于多个指标的综合评分
            reply_improvement = final.reply_count - baseline.reply_count
            user_improvement = final.unique_users - baseline.unique_users

            # 标准化改进
            reply_score = min(reply_improvement / 5, 1.0)  # 5个回复为满分
            user_score = min(user_improvement / 3, 1.0)  # 3个新用户为满分

            # 质量指标
            quality_score = (final.sentiment_score + final.sustained_attention + final.conversation_depth) / 3

            # 综合评分
            success_score = reply_score * 0.3 + user_score * 0.3 + quality_score * 0.4

            return max(0.0, min(1.0, success_score))

        except Exception as e:
            logger.error(f"成功度计算失败: {e}")
            return 0.0

    def _analyze_engagement_trend(self, baseline: EngagementMetrics, final: EngagementMetrics) -> str:
        """分析参与趋势"""
        try:
            reply_change = final.reply_count - baseline.reply_count
            user_change = final.unique_users - baseline.unique_users

            if reply_change > 2 and user_change > 0:
                return "increasing"
            elif reply_change < -1 or user_change < 0:
                return "decreasing"
            else:
                return "stable"

        except Exception as e:
            logger.error(f"趋势分析失败: {e}")
            return "stable"

    def _generate_recommendations(self, success_score: float, trend: str, metrics: EngagementMetrics) -> List[str]:
        """生成建议"""
        recommendations = []

        if success_score < 0.3:
            recommendations.append("考虑终止话题或重新发起")
            if metrics.reply_count < 2:
                recommendations.append("话题吸引力不足，建议调整话题内容")
        elif success_score < 0.6:
            recommendations.append("话题进展一般，可考虑发送跟进消息")
            if trend == "decreasing":
                recommendations.append("参与度下降，建议增加互动")
        else:
            recommendations.append("话题进展良好，继续保持")
            if metrics.sustained_attention > 0.7:
                recommendations.append("用户参与度很高，建议继续深化讨论")

        return recommendations

    def _decide_next_action(self, success_score: float, trend: str, metrics: EngagementMetrics) -> str:
        """决定下一步行动"""
        try:
            if success_score < 0.2:
                return "terminate"
            elif success_score < 0.5 and trend == "decreasing":
                return "retry"
            elif success_score >= 0.7 and metrics.reply_count >= 3:
                return "continue"
            elif success_score >= 0.5:
                return "followup"
            else:
                return "continue"

        except Exception as e:
            logger.error(f"行动决策失败: {e}")
            return "continue"

    def get_monitoring_status(self) -> Dict[str, Any]:
        """获取监测状态"""
        return {"active_monitoring": len(self.monitoring_topics), "topics": list(self.monitoring_topics.keys())}
