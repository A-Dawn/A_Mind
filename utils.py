"""
A_mind工具函数

包含全局数据库管理器等工具函数
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import time

# 向后兼容：保持全局数据库管理器实例
_db_manager_instance = None


def get_global_db_manager():
    """获取全局数据库管理器实例（向后兼容）"""
    global _db_manager_instance
    if _db_manager_instance is None:
        # 创建插件自己的业务逻辑管理器
        try:
            from .repositories.database_manager import DatabaseManager
        except ImportError:
            from pathlib import Path
            import sys

            plugin_path = Path(__file__).parent
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))
            from repositories.database_manager import DatabaseManager
        _db_manager_instance = DatabaseManager()
    return _db_manager_instance


def resolve_stream_config_to_stream_id(stream_config_str: str) -> str:
    """将 `platform:id:type` 或已存在的 session_id 解析为真实聊天流 ID。"""
    normalized_stream_config = str(stream_config_str or "").strip()
    if not normalized_stream_config:
        return ""

    try:
        from src.chat.message_receive.chat_manager import chat_manager

        if chat_manager.get_existing_session_by_session_id(normalized_stream_config):
            return normalized_stream_config
    except Exception:
        pass

    parts = [part.strip() for part in normalized_stream_config.split(":")]
    if len(parts) != 3:
        return ""

    platform, target_id, stream_type = parts
    if not platform or not target_id:
        return ""

    stream_type = stream_type.lower()
    if stream_type == "group":
        chat_type = "group"
    elif stream_type in {"private", "person", "user"}:
        chat_type = "private"
    else:
        return ""

    try:
        from src.chat.message_receive.chat_manager import chat_manager

        session_ids = chat_manager.resolve_session_ids_by_target(
            platform=platform,
            target_id=target_id,
            chat_type=chat_type,
        )
    except Exception:
        return ""

    return sorted(session_ids)[0] if session_ids else ""


def _truncate_text(text: str, max_chars: int) -> str:
    normalized_text = str(text or "").strip()
    if max_chars <= 0 or len(normalized_text) <= max_chars:
        return normalized_text
    return normalized_text[:max_chars].rstrip() + "..."


def get_amind_scene_context(stream_id: str = "", *, include_personality: bool = True) -> str:
    """构建 A_Mind 直接发言使用的基础场景与人设上下文。"""
    normalized_stream_id = str(stream_id or "").strip()
    lines: List[str] = [f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]

    try:
        from src.config.config import global_config

        bot_name = getattr(global_config.bot, "nickname", "") or "麦麦"
        alias_names = getattr(global_config.bot, "alias_names", None) or []
        alias_text = f"；别名：{', '.join(alias_names)}" if alias_names else ""
        lines.append(f"机器人身份：名字是{bot_name}{alias_text}")

        personality_config = getattr(global_config, "personality", None)
        if include_personality and personality_config:
            if getattr(personality_config, "personality", None):
                lines.append(f"人设：{personality_config.personality}")
            if getattr(personality_config, "reply_style", None):
                lines.append(f"表达风格：{personality_config.reply_style}")
            plan_style = getattr(personality_config, "plan_style", None)
            if plan_style:
                lines.append(f"行为规则：{plan_style}")

        is_group_chat: Optional[bool] = None
        chat_name = ""
        if normalized_stream_id:
            try:
                from src.chat.message_receive.chat_manager import chat_manager

                chat_session = chat_manager.get_existing_session_by_session_id(normalized_stream_id)
                if chat_session is not None:
                    is_group_chat = getattr(chat_session, "is_group_session", None)
                    chat_name = (
                        getattr(chat_session, "stream_name", "")
                        or getattr(chat_session, "display_name", "")
                        or getattr(chat_session, "chat_name", "")
                    )
            except Exception:
                pass

        if normalized_stream_id:
            chat_type = "群聊" if is_group_chat is True else "私聊" if is_group_chat is False else "未知类型聊天"
            if chat_name:
                lines.append(f"当前聊天流：{chat_name}（{chat_type}，{normalized_stream_id}）")
            else:
                lines.append(f"当前聊天流：{chat_type}（{normalized_stream_id}）")

        chat_config = getattr(global_config, "chat", None)
        if chat_config:
            if is_group_chat is True and getattr(chat_config, "group_chat_prompt", None):
                lines.append(f"群聊通用注意事项：{chat_config.group_chat_prompt}")
            elif is_group_chat is False and getattr(chat_config, "private_chat_prompts", None):
                lines.append(f"私聊通用注意事项：{chat_config.private_chat_prompts}")

        if normalized_stream_id:
            try:
                from src.common.utils.utils_config import ChatConfigUtils

                chat_prompt = ChatConfigUtils.get_chat_prompt_for_chat(normalized_stream_id, is_group_chat).strip()
                if chat_prompt:
                    lines.append(f"当前聊天额外注意事项：{chat_prompt}")
            except Exception:
                pass
    except Exception:
        pass

    return "\n".join(line for line in lines if str(line or "").strip())


async def get_recent_chat_context(stream_id: str, *, limit: int = 12, lookback_seconds: int = 7200) -> List[Dict[str, Any]]:
    """读取目标聊天流近期消息，供 A_Mind 直接发言 prompt 使用。"""
    normalized_stream_id = str(stream_id or "").strip()
    if not normalized_stream_id or limit <= 0:
        return []

    try:
        from maibot_sdk.compat.apis import message_api

        end_time = time.time()
        messages = await message_api.async_get_messages_by_time_in_chat(
            normalized_stream_id,
            end_time - max(60, int(lookback_seconds)),
            end_time,
            limit=limit,
            limit_mode="latest",
            filter_mai=False,
            filter_command=True,
        )
    except Exception:
        return []

    formatted_messages: List[Dict[str, Any]] = []
    for message in messages:
        content = getattr(message, "plain_text", getattr(message, "content", ""))
        if not str(content or "").strip():
            continue
        formatted_messages.append(
            {
                "user": getattr(message, "user_name", getattr(message, "sender_name", "Unknown")),
                "content": str(content).strip(),
                "time": getattr(message, "created_at", 0),
            }
        )

    return sorted(formatted_messages, key=lambda item: item["time"])


def format_recent_chat_context(messages: List[Dict[str, Any]], *, max_chars: int = 1600) -> str:
    """将近期消息压缩为适合注入 prompt 的文本。"""
    lines: List[str] = []
    for message in messages:
        user = str(message.get("user") or "Unknown").strip()
        content = _truncate_text(str(message.get("content") or ""), 180)
        if content:
            lines.append(f"{user}: {content}")

    return _truncate_text("\n".join(lines), max_chars)


async def search_knowledge_context(query: str, *, stream_id: str = "", limit: int = 3) -> str:
    """检索宿主记忆/知识库，失败时返回空字符串。"""
    normalized_query = _truncate_text(query, 240)
    if not normalized_query or limit <= 0:
        return ""

    try:
        from maibot_sdk.compat._context_holder import get_context

        ctx = get_context()
    except Exception:
        ctx = None

    if ctx is None:
        return ""

    try:
        result = await ctx.call_capability(
            "knowledge.search",
            query=normalized_query,
            chat_id=str(stream_id or "").strip(),
            limit=limit,
            mode="search",
        )
    except Exception:
        return ""

    if isinstance(result, dict) and result.get("success"):
        return _truncate_text(str(result.get("content") or ""), 1200)
    return ""


async def build_amind_prompt_context(
    stream_id: str = "",
    *,
    query: str = "",
    recent_limit: int = 12,
    include_knowledge: bool = True,
    include_personality: bool = True,
) -> Dict[str, str]:
    """汇总 A_Mind 直接发言链路的高价值上下文。"""
    recent_messages = await get_recent_chat_context(stream_id, limit=recent_limit)
    recent_text = format_recent_chat_context(recent_messages)
    knowledge_text = ""
    if include_knowledge:
        knowledge_text = await search_knowledge_context(query, stream_id=stream_id, limit=3)

    return {
        "scene": get_amind_scene_context(stream_id, include_personality=include_personality),
        "recent_chat": recent_text,
        "knowledge": knowledge_text,
    }


async def send_amind_text_to_stream(stream_id: str, content: str) -> Tuple[bool, str]:
    """由 A_Mind 直接向聊天流发送文本，不经过 Maisaka 主动发言链路。"""
    normalized_stream_id = str(stream_id or "").strip()
    normalized_content = str(content or "").strip()
    if not normalized_stream_id:
        return False, "缺少 stream_id"
    if not normalized_content:
        return False, "缺少发送内容"

    try:
        from maibot_sdk.compat.apis import send_api

        ok = await send_api.text_to_stream(normalized_content, stream_id=normalized_stream_id)
    except Exception as exc:
        return False, str(exc)

    if ok:
        return True, ""
    return False, "send.text 能力返回失败"
