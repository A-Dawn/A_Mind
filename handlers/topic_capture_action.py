from typing import Any, Dict, List, Tuple
import json
import re
import time

from maibot_sdk.compat import BaseAction
from maibot_sdk.compat.apis import llm_api, message_api

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
    from ..utils import build_amind_prompt_context
    from ..utils import send_amind_text_to_stream
except ImportError:
    from core.amind_logger import get_logger
    from utils import build_amind_prompt_context
    from utils import send_amind_text_to_stream

logger = get_logger(__name__)


class TopicCaptureAction(BaseAction):
    """
    话题捕捉动作
    根据最近的聊天上下文，使用LLM判断是否需要介入（捕捉话题）。
    如果需要介入，则直接生成回复并发送。
    """
    action_name = "topic_capture"
    action_description = "根据聊天上下文判断是否需要进行话题捕捉介入"
    action_parameters: Dict[str, Any] = {}
    action_require = ["读取最近聊天上下文", "使用LLM判断是否适合介入"]
    associated_types = ["text", "message"]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 获取plan_name，默认为plan1
        self.plan_name = kwargs.get("plan_name", "plan1")
        # 允许外部注入config_manager
        self.config_manager = getattr(kwargs.get("auto_initiate_action"), "config_manager", None)

    def get_config(self, key: str, default=None):
        """获取配置"""
        if self.config_manager:
            return self.config_manager.get(key, default)
        
        # Fallback to parent's get_config if available (BaseAction usually has it if initialized by plugin system)
        try:
            return super().get_config(key, default)
        except AttributeError:
            return default

    async def execute(self) -> Tuple[bool, str]:
        """执行话题捕捉"""
        try:
            stream_id = self.chat_stream.stream_id
            logger.info(f"[A_Mind] [{self.plan_name}] 开始执行话题捕捉分析，流ID: {stream_id}")

            # 1. 获取最近消息上下文
            min_messages = self.get_config(f"{self.plan_name}.topic_capture.min_messages", 5)
            # 获取最近20条消息作为上下文
            recent_messages = await self._get_recent_messages(stream_id, limit=20)
            
            if len(recent_messages) < min_messages:
                return False, f"上下文消息过少 ({len(recent_messages)} < {min_messages})，跳过捕捉"

            logger.debug(f"[A_Mind] 获取到 {len(recent_messages)} 条上下文消息")

            # 2. 调用LLM进行分析
            should_intervene, reasoning, reply_content = await self._analyze_context(recent_messages, stream_id)

            if not should_intervene:
                return False, f"LLM判断无需介入: {reasoning}"

            # 3. 介入：发送回复
            if not reply_content:
                return False, "LLM决定介入但未生成回复内容"

            logger.info(f"[A_Mind] 话题捕捉触发！原因: {reasoning}")
            logger.info(f"[A_Mind] 准备发送回复: {reply_content[:50]}...")

            ok, send_reason = await send_amind_text_to_stream(stream_id, reply_content)
            if not ok:
                return False, f"消息发送失败: {send_reason}"

            return True, f"捕捉成功，已回复。原因: {reasoning}"

        except Exception as e:
            logger.error(f"[A_Mind] 话题捕捉执行异常: {e}")
            return False, f"执行异常: {str(e)}"

    async def _get_recent_messages(self, stream_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近消息"""
        try:
            end_time = time.time()
            start_time = end_time - 3600
            messages = await message_api.async_get_messages_by_time_in_chat(
                stream_id,
                start_time,
                end_time,
                limit=limit,
                limit_mode="latest",
                filter_mai=False,
                filter_command=True,
            )
            
            formatted_messages = []
            for msg in messages:
                # 过滤掉自己发的消息 (可选，取决于是否想让Bot意识到自己的存在)
                # 假设 msg.user_id 可以用来区分。这里暂时都保留。
                
                content = getattr(msg, "plain_text", getattr(msg, "content", ""))
                user_name = getattr(msg, "user_name", getattr(msg, "sender_name", "Unknown"))
                
                if content:
                    formatted_messages.append(
                        {
                            "user": user_name,
                            "content": content,
                            "time": getattr(msg, "created_at", 0),
                        }
                    )
            
            # 按时间正序排列
            return sorted(formatted_messages, key=lambda x: x["time"])

        except Exception as e:
            logger.warning(f"[A_Mind] 获取历史消息失败: {e}")
            return []

    async def _analyze_context(self, messages: List[Dict[str, Any]], stream_id: str = "") -> Tuple[bool, str, str]:
        """
        使用LLM分析上下文
        Returns: (should_intervene, reasoning, reply_content)
        """
        try:
            # 构建上下文文本
            context_text = ""
            for msg in messages:
                context_text += f"{msg['user']}: {msg['content']}\n"
            prompt_context = await build_amind_prompt_context(
                stream_id,
                query=context_text,
                recent_limit=0,
                include_knowledge=True,
            )
            scene_context = prompt_context.get("scene") or "无"
            knowledge_context = prompt_context.get("knowledge") or "无"

            # 构建Prompt
            prompt = f"""You are an advanced Conversation Analyst and Participant for a chat group.
Your task is to observe the recent conversation history and decide if you should intervene to add value.

Current identity, scene and constraints:
<scene>
{scene_context}
</scene>

Relevant memory or knowledge:
<knowledge>
{knowledge_context}
</knowledge>

Here is the recent conversation context:
<context>
{context_text}
</context>

You should intervene (return TRUE) ONLY if the conversation falls into one of these high-value categories, based on the following dimensions:

1.  **Information Gap (Fact Check)**: Users are speculating about facts/dates/data that are unsure, and you can provide the correct answer or clarity.
2.  **Implicit Help (Q&A Rescue)**: Someone asked a specific question or sought help, but was ignored by others. You can answer them.
3.  **Emotional Resonance (Empathy)**: Someone expressed strong emotions (sadness, excitement, frustration) but received little response. You can provide empathy or celebration.
4.  **Debate/Conflict (Mediation)**: A discussion is stuck in a deadlock or "repeating" loop. You can provide a neutral, humorous, or fresh perspective to break the ice.
5.  **Topic Decay (Revival)**: A potentially interesting topic (deep/tech/science/creative) was started but died prematurely without discussion. You can ask a follow-up question or add a fun fact to revive it.

**Rules**:
- Do NOT intervene if the conversation is flowing naturally and users are interacting happily.
- Do NOT intervene just to say "hello" or generic pleasantries.
- Do NOT intervene if you have nothing meaningful to add.
- Be selective. Silence is better than noise.
- If you reply, follow the identity, chat scene and language style above.
- Use memory/knowledge only when it naturally helps; do not dump background material.
- The reply must be Simplified Chinese unless the recent conversation strongly requires otherwise.

**Output Format**:
You must output a JSON object with the following fields:
- "decision": boolean (true if you want to intervene, false otherwise)
- "reasoning": string (brief explanation of which dimension matched and why)
- "reply": string (the actual content you want to send. If decision is false, leave empty)

Output JSON ONLY.
"""
            # 调用LLM
            model_config = {
                "model_name": self.get_config("llm.model_name", "utils"),
                "temperature": 0.5,  # 稍低温度以保持分析理性
                "max_tokens": 1000,
            }

            logger.debug("[A_Mind] 调用LLM进行语境分析...")
            available_models = llm_api.get_available_models()
            selected_model = available_models.get(model_config["model_name"])
            if not selected_model and available_models:
                selected_model = next(iter(available_models.values()))

            if not selected_model:
                return False, "No available model", ""

            ok, response, _, _ = await llm_api.generate_with_model(
                prompt=prompt,
                model_config=selected_model,
                request_type="A_mind.topic_capture",
                temperature=model_config["temperature"],
                max_tokens=model_config["max_tokens"],
            )
            if not ok:
                return False, f"LLM call failed: {response}", ""
            
            # 解析JSON
            # 尝试提取JSON块
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                    decision = result.get("decision", False)
                    reasoning = result.get("reasoning", "No reason provided")
                    reply = result.get("reply", "")
                    
                    return decision, reasoning, reply
                    
                except json.JSONDecodeError:
                    logger.warning(f"[A_Mind] LLM返回的JSON解析失败: {response}")
            else:
                logger.warning(f"[A_Mind] LLM未返回JSON格式: {response}")

            return False, "Failed to parse LLM response", ""

        except Exception as e:
            logger.error(f"[A_Mind] LLM分析失败: {e}")
            return False, str(e), ""
