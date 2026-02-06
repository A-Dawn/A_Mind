"""
信息检索器 - 负责互联网搜索和知识库查询
"""

import asyncio
import json
import time
from typing import List, Dict, Any, Optional

# 中文分词支持
try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

# 信息检索相关导入
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    from ..models.search import SearchResult, KnowledgeItem
    from ..models.topic import Topic
    from ..database import get_db_connection
except ImportError:
    import sys
    from pathlib import Path
    plugin_path = Path(__file__).parent.parent
    if str(plugin_path) not in sys.path:
        sys.path.insert(0, str(plugin_path))
    from models.search import SearchResult, KnowledgeItem
    from models.topic import Topic
    from database import get_db_connection

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

logger = get_logger(__name__)


class InformationRetriever:
    """信息检索器 - 负责互联网搜索和知识库查询"""

    def __init__(self, config_manager):
        """初始化信息检索器

        Args:
            config_manager: 配置管理器实例
        """
        self.config = config_manager
        self.session = None
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

    async def search_internet(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """互联网搜索 - 支持多种搜索引擎"""
        try:
            if not REQUESTS_AVAILABLE:
                logger.warning("[A_Mind] requests库不可用，无法进行互联网搜索")
                return []

            # 获取搜索引擎配置
            search_engine = self.config.get("internet_search.engine", "duckduckgo")
            logger.info(f"[A_Mind] 使用搜索引擎: {search_engine}")

            # 根据配置选择搜索引擎
            if search_engine == "tavily":
                return await self._search_tavily(query, max_results)
            elif search_engine == "searxng":
                return await self._search_searxng(query, max_results)
            elif search_engine == "duckduckgo":
                return await self._search_duckduckgo(query, max_results)
            else:
                logger.warning(f"[A_Mind] 不支持的搜索引擎: {search_engine}，使用DuckDuckGo作为默认")
                return await self._search_duckduckgo(query, max_results)

        except Exception as e:
            logger.error(f"[A_Mind] 互联网搜索失败: {e}")
            return []

    async def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """使用DuckDuckGo进行搜索"""
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={query}"
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.get(search_url, timeout=10)
            )

            if response.status_code != 200:
                logger.error(f"[A_Mind] DuckDuckGo搜索请求失败: {response.status_code}")
                return []

            # 解析搜索结果
            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            for result in soup.find_all("div", class_="result")[:max_results]:
                title_elem = result.find("h2", class_="result__title")
                snippet_elem = result.find("a", class_="result__snippet")
                url_elem = result.find("a", class_="result__url")

                if title_elem and url_elem:
                    title = title_elem.get_text(strip=True)
                    url = url_elem.get("href", "")
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                    # 清理URL
                    if url.startswith("//duckduckgo.com/l/?uddg="):
                        url = url.split("uddg=")[1].split("&")[0]

                    results.append(
                        SearchResult(title=title, url=url, snippet=snippet, source="DuckDuckGo", relevance_score=0.8)
                    )

            logger.info(f"[A_Mind] DuckDuckGo搜索完成，找到{len(results)}个结果")
            return results

        except Exception as e:
            logger.error(f"[A_Mind] DuckDuckGo搜索失败: {e}")
            return []

    async def _search_tavily(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """使用Tavily进行搜索（支持多Key轮询）"""
        try:
            api_keys_config = self.config.get("internet_search.tavily_api_key", "")
            
            # 统一处理配置格式：可能是字符串或列表
            api_keys: List[str] = []
            if isinstance(api_keys_config, str):
                if api_keys_config.strip():
                     api_keys = [api_keys_config.strip()]
            elif isinstance(api_keys_config, list):
                api_keys = [str(k).strip() for k in api_keys_config if str(k).strip()]
            
            if not api_keys:
                logger.warning("[A_Mind] Tavily API密钥未配置，跳过Tavily搜索")
                return []

            base_url = self.config.get("internet_search.tavily_base_url", "https://api.tavily.com")
            
            # 尝试轮询所有 Key
            last_error = None
            for key_index, api_key in enumerate(api_keys):
                try:
                    # logger.debug(f"[A_Mind] 尝试使用 Tavily Key #{key_index + 1}...") # 避免打印 Key
                    
                    # 构建请求
                    payload = {
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "include_images": False,
                        "include_answer": False,
                        "include_raw_content": False,
                        "max_results": max_results,
                        "include_domains": [],
                        "exclude_domains": [],
                    }

                    headers = {"Content-Type": "application/json"}

                    response = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.session.post(f"{base_url}/search", json=payload, headers=headers, timeout=15)
                    )

                    if response.status_code == 200:
                         data = response.json()
                         results = []

                         # 解析Tavily响应
                         for item in data.get("results", [])[:max_results]:
                             title = item.get("title", "")
                             url = item.get("url", "")
                             content = item.get("content", "")

                             if title and url:
                                 results.append(
                                     SearchResult(
                                         title=title,
                                         url=url,
                                         snippet=content[:200],  # 限制摘要长度
                                         source="Tavily",
                                         relevance_score=0.9,  # Tavily结果质量较高
                                     )
                                 )

                         logger.info(f"[A_Mind] Tavily搜索完成 (使用Key #{key_index + 1})，找到{len(results)}个结果")
                         return results
                    
                    # 如果是认证错误或额度错误，尝试下一个 Key
                    elif response.status_code in [401, 403, 429]:
                        logger.warning(f"[A_Mind] Tavily Key #{key_index + 1} 请求失败 (Status: {response.status_code})，尝试下一个 Key...")
                        last_error = f"Status: {response.status_code}"
                        continue
                    
                    else:
                        logger.error(f"[A_Mind] Tavily搜索请求失败: {response.status_code}")
                        last_error = f"Status: {response.status_code}"
                        # 其他错误可能不需要重试，但为了稳健继续尝试下一个也无妨，或者直接返回
                        # 这里选择继续尝试，以防万一
                        continue

                except Exception as loop_e:
                    logger.warning(f"[A_Mind] Tavily Key #{key_index + 1} 发生异常: {loop_e}")
                    last_error = str(loop_e)
                    continue

            logger.error(f"[A_Mind] 所有 Tavily Key 均尝试失败。最后错误: {last_error}")
            return []

        except Exception as e:
            logger.error(f"[A_Mind] Tavily搜索逻辑异常: {e}")
            return []

    async def _search_searxng(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """使用SearXNG进行搜索"""
        try:
            base_url = self.config.get("internet_search.searxng_base_url", "")
            if not base_url:
                logger.warning("[A_Mind] SearXNG基础URL未配置，跳过SearXNG搜索")
                return []

            # 构建搜索URL
            search_params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "engines": "google,bing,duckduckgo",
                "language": "zh-CN",
                "safesearch": "2",
            }

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.get(base_url, params=search_params, timeout=15)
            )

            if response.status_code != 200:
                logger.error(f"[A_Mind] SearXNG搜索请求失败: {response.status_code}")
                return []

            data = response.json()
            results = []

            # 解析SearXNG响应
            for item in data.get("results", [])[:max_results]:
                title = item.get("title", "")
                url = item.get("url", "")
                content = item.get("content", "")

                if title and url:
                    results.append(
                        SearchResult(
                            title=title,
                            url=url,
                            snippet=content[:200],  # 限制摘要长度
                            source="SearXNG",
                            relevance_score=0.85,
                        )
                    )

            logger.info(f"[A_Mind] SearXNG搜索完成，找到{len(results)}个结果")
            return results

        except Exception as e:
            logger.error(f"[A_Mind] SearXNG搜索失败: {e}")
            return []

    async def search_knowledge_base(
        self, query: str, category: Optional[str] = None, max_results: int = 10
    ) -> List[KnowledgeItem]:
        """知识库搜索"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 构建查询
            sql = """
                SELECT * FROM amind_knowledge
                WHERE (title LIKE ? OR content LIKE ?)
            """
            params = [f"%{query}%", f"%{query}%"]

            if category:
                sql += " AND category = ?"
                params.append(category)

            sql += " ORDER BY relevance_score DESC, updated_at DESC LIMIT ?"
            params.append(max_results)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                results.append(
                    KnowledgeItem(
                        id=row[0],
                        title=row[1],
                        content=row[2],
                        category=row[3],
                        tags=json.loads(row[4]) if row[4] else [],
                        source=row[5],
                        relevance_score=row[6],
                        created_at=row[7],
                        updated_at=row[8],
                    )
                )

            logger.info(f"[A_Mind] 知识库搜索完成，找到{len(results)}个结果")
            return results

        except Exception as e:
            logger.error(f"[A_Mind] 知识库搜索失败: {e}")
            return []

    async def add_knowledge_item(self, item: KnowledgeItem) -> bool:
        """添加知识库条目"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO amind_knowledge
                (title, content, category, tags, source, relevance_score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item.title,
                    item.content,
                    item.category,
                    json.dumps(item.tags),
                    item.source,
                    item.relevance_score,
                    item.created_at,
                    item.updated_at,
                ),
            )

            conn.commit()
            logger.info(f"[A_Mind] 知识库条目添加成功: {item.title}")
            return True

        except Exception as e:
            logger.error(f"[A_Mind] 添加知识库条目失败: {e}")
            conn.rollback()
            return False

    async def update_knowledge_relevance(self, item_id: int, new_score: float) -> bool:
        """更新知识条目相关性分数"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE amind_knowledge
                SET relevance_score = ?, updated_at = ?
                WHERE id = ?
            """,
                (new_score, time.time(), item_id),
            )

            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(f"[A_Mind] 知识条目相关性更新成功: ID={item_id}, 分数={new_score}")
            return success

        except Exception as e:
            logger.error(f"[A_Mind] 更新知识条目相关性失败: {e}")
            conn.rollback()
            return False

    async def get_relevant_information(self, topic: Topic, context: str = "") -> Dict[str, Any]:
        """获取话题相关信息"""
        try:
            # 构建搜索查询
            search_query = f"{topic.title} {topic.description}"

            # 并行执行搜索
            internet_results, knowledge_results = await asyncio.gather(
                self.search_internet(search_query, max_results=3),
                self.search_knowledge_base(search_query, max_results=5),
            )

            # 整理结果
            relevant_info = {
                "internet_results": internet_results,
                "knowledge_results": knowledge_results,
                "search_query": search_query,
                "total_results": len(internet_results) + len(knowledge_results),
            }

            logger.info(
                f"[A_Mind] 获取相关信息完成: 互联网{len(internet_results)}个, 知识库{len(knowledge_results)}个"
            )
            return relevant_info

        except Exception as e:
            logger.error(f"[A_Mind] 获取相关信息失败: {e}")
            return {
                "internet_results": [],
                "knowledge_results": [],
                "search_query": "",
                "total_results": 0,
                "error": str(e),
            }
