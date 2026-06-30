"""Google Trends 搜尋熱度模組。"""

from .collector import InterestFetcher, fetch_ticker_interest, pytrends_fetcher

__all__ = ["InterestFetcher", "fetch_ticker_interest", "pytrends_fetcher"]
