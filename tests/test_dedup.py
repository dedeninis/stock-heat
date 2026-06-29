from stock_heat.collectors.news.dedup import (
    hamming_distance,
    is_near_duplicate,
    normalize_url,
    simhash,
)


def test_normalize_url_strips_tracking_and_www():
    a = normalize_url("https://www.cnyes.com/news/id/123?utm_source=fb&fbclid=xyz")
    b = normalize_url("http://cnyes.com/news/id/123/")
    assert a == b == "https://cnyes.com/news/id/123"


def test_normalize_url_keeps_meaningful_query_sorted():
    assert normalize_url("https://x.com/a?b=2&a=1") == "https://x.com/a?a=1&b=2"


def test_simhash_identical_text_zero_distance():
    text = "台積電法說會釋出展望，外資調升目標價，盤中股價走高。"
    assert hamming_distance(simhash(text), simhash(text)) == 0


def test_simhash_near_duplicate_detected():
    a = "台積電法說會釋出展望，外資調升目標價，盤中股價走高。"
    b = "台積電法說會釋出展望，外資調升目標價，盤中股價走高！"  # 僅標點差異
    assert is_near_duplicate(simhash(a), simhash(b), threshold=3)


def test_simhash_distinct_text_not_duplicate():
    a = "台積電法說會釋出樂觀展望，外資調升目標價。"
    b = "某生技公司新藥臨床試驗失敗，股價跌停。"
    assert not is_near_duplicate(simhash(a), simhash(b), threshold=3)
