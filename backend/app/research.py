"""Web research via DuckDuckGo (no API key). Only search snippets + URLs are used - pages are never
fetched server-side, which avoids SSRF and keeps citations traceable to a visible URL."""
from .config import settings


def web_search(query: str, n: int = 4) -> list[dict]:
    if not settings.WEB_SEARCH:
        return []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as d:
            res = d.text(query, max_results=n) or []
        return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in res if r.get("href")]
    except Exception:  # network/rate-limit problems must never break the chat
        return []
