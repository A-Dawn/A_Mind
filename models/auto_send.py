"""
自动发送相关数据模型

包含AutoSendRequest、SendResult等数据模型
"""

import time
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class AutoSendRequest:
    """自动发送请求"""

    topic_id: int = 0
    content: str = ""
    send_type: str = "initiate"  # initiate, followup, reminder
    priority: int = 1
    scheduled_time: float = 0
    stream_id: Optional[str] = None  # 目标聊天流ID（必须提供，否则无法定向发送）
    conditions: Dict[str, Any] = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = {}
        if self.scheduled_time == 0:
            self.scheduled_time = time.time()


@dataclass
class SendResult:
    """发送结果"""

    success: bool = False
    message_id: str = ""
    error_message: str = ""
    sent_at: float = 0
    retry_count: int = 0

    def __post_init__(self):
        if self.sent_at == 0:
            self.sent_at = time.time()

