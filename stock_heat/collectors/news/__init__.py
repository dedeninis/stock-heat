"""財經新聞擷取模組（docs/03 §4）。"""

from .collector import NewsCollector, collect_all_news
from .sources import NewsSource, load_news_sources

__all__ = ["NewsCollector", "collect_all_news", "NewsSource", "load_news_sources"]
