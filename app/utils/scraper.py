"""
网页抓取工具模块
基于 requests + BeautifulSoup 实现网页数据抓取，支持两步路平台和通用网页解析
"""
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup
from app.utils.logger import logger

# 请求头，模拟浏览器访问
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# 两步路平台搜索 URL
TWO_BULU_SEARCH_URL = "https://www.2bulu.com/track/search.htm"


def fetch_page(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: int = 15,
    retries: int = 2,
) -> Optional[str]:
    """
    通用网页抓取方法
    Args:
        url: 目标 URL
        params: 查询参数
        headers: 自定义请求头
        timeout: 超时时间（秒）
        retries: 重试次数
    Returns:
        网页 HTML 文本，失败返回 None
    """
    _headers = {**DEFAULT_HEADERS, **(headers or {})}

    for attempt in range(retries + 1):
        try:
            response = requests.get(
                url, params=params, headers=_headers, timeout=timeout
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException as e:
            logger.warning(f"网页抓取失败 (第 {attempt + 1}/{retries + 1} 次): {url} - {e}")
            if attempt < retries:
                time.sleep(1 * (attempt + 1))
    return None


def parse_html(html: str) -> BeautifulSoup:
    """解析 HTML 文本为 BeautifulSoup 对象"""
    return BeautifulSoup(html, "html.parser")


def search_2bulu_routes(keyword: str) -> Optional[str]:
    """
    搜索两步路平台徒步路线
    Args:
        keyword: 路线关键词，如 "武功山"
    Returns:
        搜索结果页 HTML，失败返回 None
    """
    params = {
        "keyword": keyword,
        "page": 1,
    }
    logger.info(f"两步路路线搜索: {keyword}")
    return fetch_page(TWO_BULU_SEARCH_URL, params=params)


def extract_2bulu_route_data(html: str) -> list[dict]:
    """
    从两步路搜索结果页提取路线结构化数据
    Args:
        html: 搜索结果页 HTML
    Returns:
        路线数据列表
    """
    soup = parse_html(html)
    routes = []

    # 尝试多种可能的 DOM 结构提取路线信息
    # 两步路页面结构可能变化，需做兼容处理
    track_items = (
        soup.select(".track-item")
        or soup.select(".search-result-item")
        or soup.select('[class*="track"]')
    )

    if not track_items:
        # 尝试从页面 script 标签中提取 JSON 数据
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "trackList" in script.string:
                logger.info("从 script 标签中检测到路线数据")
                break

    for item in track_items[:10]:  # 最多取 10 条
        route = {
            "name": _extract_text(item, [".track-title", "h3", "h4", ".title"]),
            "distance": _extract_text(item, [".distance", '[data-field="distance"]']),
            "elevation_gain": _extract_text(item, [".elevation", ".ascent", '[data-field="elevation"]']),
            "max_altitude": _extract_text(item, [".max-altitude", ".altitude"]),
            "difficulty": _extract_text(item, [".difficulty", ".level", ".grade"]),
            "duration": _extract_text(item, [".duration", ".time", ".cost-time"]),
            "best_season": _extract_text(item, [".season", ".best-time"]),
            "summary": _extract_text(item, [".summary", ".desc", ".description", "p"]),
            "rating": _extract_text(item, [".rating", ".score", ".star"]),
            "link": _extract_href(item, "a"),
        }
        # 过滤掉名称为空的无效条目
        if route["name"]:
            routes.append(route)

    logger.info(f"从两步路提取到 {len(routes)} 条路线")
    return routes


def _extract_text(soup, selectors: list[str]) -> str:
    """尝试多个选择器提取文本"""
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            return elem.get_text(strip=True)
    return ""


def _extract_href(soup, selector: str) -> str:
    """提取链接地址"""
    elem = soup.select_one(selector)
    if elem and elem.get("href"):
        href = elem["href"]
        if href.startswith("/"):
            href = "https://www.2bulu.com" + href
        return href
    return ""