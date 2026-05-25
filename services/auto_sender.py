"""
自动发送器 - 负责将生成的内容发送到聊天流
"""

import time
from typing import Dict, Any, List

try:
    from ..models.auto_send import AutoSendRequest, SendResult
    from ..utils import get_global_db_manager
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from models.auto_send import AutoSendRequest, SendResult
    from utils import get_global_db_manager

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger
from src.plugin_system.apis import send_api

logger = get_logger(__name__)


class AutoSender:
    """自动发送器 - 负责将生成的内容发送到聊天流"""

    def __init__(self, db_manager=None):
        self.send_queue = []
        self.is_running = False
        self.db_manager = db_manager or get_global_db_manager()

    async def schedule_send(self, request: AutoSendRequest) -> bool:
        """调度自动发送"""
        try:
            # 验证请求
            if not self._validate_send_request(request):
                logger.error(f"[A_Mind] 发送请求验证失败: {request.topic_id}")
                return False

            # 添加到队列
            self.send_queue.append(request)

            # 检查是否需要立即发送
            if self._should_send_immediately(request):
                return await self._execute_send(request)
            else:
                logger.info(
                    f"[A_Mind] 发送请求已排队: 话题{request.topic_id}, 计划发送时间{time.strftime('%H:%M:%S', time.localtime(request.scheduled_time))}"
                )
                return True

        except Exception as e:
            logger.error(f"调度发送失败: {e}")
            return False

    async def process_queue(self):
        """处理发送队列"""
        try:
            if self.is_running:
                return

            self.is_running = True
            current_time = time.time()

            # 处理到期请求
            pending_requests = []
            for request in self.send_queue:
                if request.scheduled_time <= current_time:
                    # 检查发送条件
                    if await self._check_send_conditions(request):
                        success = await self._execute_send(request)
                        if not success and request.retry_count < request.max_retries:
                            # 重试逻辑
                            request.retry_count += 1
                            request.scheduled_time = current_time + (request.retry_count * 300)  # 5分钟递增延迟
                            pending_requests.append(request)
                    else:
                        # 条件不满足，重新排队
                        pending_requests.append(request)
                else:
                    pending_requests.append(request)

            self.send_queue = pending_requests
            self.is_running = False

        except Exception as e:
            logger.error(f"处理发送队列失败: {e}")
            self.is_running = False

    async def _execute_send(self, request: AutoSendRequest) -> bool:
        """执行发送"""
        try:
            if not request.stream_id:
                logger.error(f"[A_Mind] 发送请求缺少 stream_id: topic={request.topic_id}")
                return False

            # 构建发送内容
            send_content = await self._build_send_content(request)

            if not send_content:
                logger.error(f"[A_Mind] 构建发送内容失败: {request.topic_id}")
                return False

            # 发送到聊天流（真实发送）
            ok = await send_api.text_to_stream(send_content, stream_id=request.stream_id)
            if not ok:
                logger.error(f"[A_Mind] 自动发送失败: stream_id={request.stream_id}, topic={request.topic_id}")
                return False

            logger.info(f"[A_Mind] 自动发送成功: stream_id={request.stream_id}, content={send_content[:100]}...")

            # 记录发送结果
            await self._record_send_result(
                request,
                SendResult(
                    success=True,
                    message_id=f"auto_{request.topic_id}_{int(time.time())}",
                    sent_at=time.time(),
                    retry_count=request.retry_count,
                ),
            )

            # 更新话题统计
            self._update_topic_send_stats(request.topic_id, request.send_type)

            return True

        except Exception as e:
            logger.error(f"执行发送失败: {e}")

            # 记录失败结果
            await self._record_send_result(
                request,
                SendResult(success=False, error_message=str(e), sent_at=time.time(), retry_count=request.retry_count),
            )

            return False

    def _validate_send_request(self, request: AutoSendRequest) -> bool:
        """验证发送请求"""
        try:
            if not request.topic_id or not request.content:
                return False

            if not request.stream_id:
                return False

            if request.send_type not in ["initiate", "followup", "reminder"]:
                return False

            if request.priority < 1 or request.priority > 5:
                return False

            return True

        except Exception as e:
            logger.error(f"验证发送请求失败: {e}")
            return False

    def _should_send_immediately(self, request: AutoSendRequest) -> bool:
        """判断是否应该立即发送"""
        try:
            current_time = time.time()
            time_diff = request.scheduled_time - current_time

            # 高优先级立即发送
            if request.priority >= 4:
                return True

            # 过期5分钟内的请求立即发送
            if time_diff <= 300:
                return True

            return False

        except Exception as e:
            logger.error(f"判断立即发送失败: {e}")
            return False

    async def _check_send_conditions(self, request: AutoSendRequest) -> bool:
        """检查发送条件"""
        try:
            conditions = request.conditions or {}
            db_manager = self.db_manager or get_global_db_manager()

            # 检查参与度条件
            min_engagement = conditions.get("min_engagement", 0.0)
            if min_engagement > 0:
                topic = db_manager.get_topic(request.topic_id)
                if topic and topic.engagement_score < min_engagement:
                    logger.info(f"[A_Mind] 发送条件不满足 - 参与度不足: {topic.engagement_score} < {min_engagement}")
                    return False

            # 检查时间条件
            min_interval_hours = conditions.get("min_interval_hours", 0)
            if min_interval_hours > 0:
                topic = db_manager.get_topic(request.topic_id)
                if topic and topic.last_auto_initiate_at:
                    hours_since_last = (time.time() - topic.last_auto_initiate_at) / 3600
                    if hours_since_last < min_interval_hours:
                        logger.info(
                            f"[A_Mind] 发送条件不满足 - 时间间隔不足: {hours_since_last:.1f} < {min_interval_hours}"
                        )
                        return False

            # 检查最大发送次数
            max_sends = conditions.get("max_sends_per_day", 5)
            today_sends = await self._get_today_send_count(request.topic_id)
            if today_sends >= max_sends:
                logger.info(f"[A_Mind] 发送条件不满足 - 今日发送次数已达上限: {today_sends} >= {max_sends}")
                return False

            return True

        except Exception as e:
            logger.error(f"检查发送条件失败: {e}")
            return False

    async def _build_send_content(self, request: AutoSendRequest) -> str:
        """构建发送内容"""
        try:
            if request.send_type == "initiate":
                return await self._build_initiate_content(request)
            elif request.send_type == "followup":
                return await self._build_followup_content(request)
            elif request.send_type == "reminder":
                return await self._build_reminder_content(request)
            else:
                return request.content

        except Exception as e:
            logger.error(f"构建发送内容失败: {e}")
            return request.content

    async def _build_initiate_content(self, request: AutoSendRequest) -> str:
        """构建自发起内容"""
        try:
            # 优先使用请求中提供的内容（如LLM生成的内容）
            if request.content and isinstance(request.content, str) and request.content.strip():
                return request.content

            topic = get_global_db_manager().get_topic(request.topic_id)
            if not topic:
                return request.content

            # 构建吸引人的发起内容（回退方案）
            content = f"💭 **{topic.title}**\n\n"
            content += f"{topic.description}\n\n"
            content += "大家有什么想法呢？欢迎分享你的观点！"

            return content

        except Exception as e:
            logger.error(f"构建发起内容失败: {e}")
            return request.content

    async def _build_followup_content(self, request: AutoSendRequest) -> str:
        """构建跟进内容"""
        try:
            topic = get_global_db_manager().get_topic(request.topic_id)
            if not topic:
                return request.content

            # 获取最近回复
            recent_replies = get_global_db_manager().get_recent_replies(request.topic_id, 3)

            if recent_replies:
                content = f"🗣️ 关于 **{topic.title}** 的讨论很热烈！\n\n"
                content += "最近的精彩观点：\n"
                for reply in recent_replies:
                    content += f"• {reply['user_name']}: {reply['message_content'][:50]}...\n"
                content += "\n还有其他想法吗？"
            else:
                content = f"🤔 关于 **{topic.title}** 好像还没什么讨论，\n"
                content += "大家对这个话题有什么看法呢？"

            return content

        except Exception as e:
            logger.error(f"构建跟进内容失败: {e}")
            return request.content

    async def _build_reminder_content(self, request: AutoSendRequest) -> str:
        """构建提醒内容"""
        try:
            topic = get_global_db_manager().get_topic(request.topic_id)
            if not topic:
                return request.content

            content = f"⏰ 提醒：**{topic.title}** 的话题还在等待大家的参与！\n\n"
            content += f"已经有 {topic.reply_count} 条讨论，参与度 {topic.engagement_score:.2f}\n\n"
            content += "快来分享你的见解吧！"

            return content

        except Exception as e:
            logger.error(f"构建提醒内容失败: {e}")
            return request.content

    async def _record_send_result(self, request: AutoSendRequest, result: SendResult):
        """记录发送结果"""
        try:
            # 这里可以扩展为将结果保存到数据库
            logger.info(
                f"[A_Mind] 发送结果记录: 话题{request.topic_id}, 成功={result.success}, 重试={result.retry_count}"
            )

        except Exception as e:
            logger.error(f"记录发送结果失败: {e}")

    def _update_topic_send_stats(self, topic_id: int, send_type: str):
        """更新话题发送统计"""
        try:
            updates = {
                "auto_initiate_count": 0,  # 会在数据库管理器中递增
                "last_auto_initiate_at": time.time(),
            }

            get_global_db_manager().update_topic(topic_id, updates)
            logger.info(f"[A_Mind] 话题发送统计已更新: {topic_id}")

        except Exception as e:
            logger.error(f"更新话题发送统计失败: {e}")

    async def _get_today_send_count(self, topic_id: int) -> int:
        """获取今日发送次数"""
        try:
            # 计算今日开始时间
            today_start = time.time() - (time.time() % 86400)

            # 这里可以查询数据库获取今日发送次数
            # 暂时返回0，表示不限制
            return 0

        except Exception as e:
            logger.error(f"获取今日发送次数失败: {e}")
            return 0

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "queue_size": len(self.send_queue),
            "is_running": self.is_running,
            "pending_sends": len([r for r in self.send_queue if r.scheduled_time > time.time()]),
        }
