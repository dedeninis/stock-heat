from stock_heat.processing.sentiment import (
    analyze_sentiment,
    analyze_ticker_sentiment,
    split_clauses,
)


def test_positive_text_positive_score():
    assert analyze_sentiment("台積電法說會樂觀，外資調升目標價，股價大漲。") > 0.3


def test_negative_text_negative_score():
    assert analyze_sentiment("公司營運衰退，獲利大跌，遭外資賣超，股價重挫。") < -0.3


def test_neutral_text_zero():
    assert analyze_sentiment("公司今日召開股東會，董事會成員出席。") == 0.0


def test_social_slang_positive():
    assert analyze_sentiment("這檔要噴了，上車賺爛！") > 0.3


def test_social_slang_negative():
    assert analyze_sentiment("慘住套房畢業，韭菜抬轎腰斬。") < -0.3


def test_negation_reverses_polarity():
    pos = analyze_sentiment("法人看好後市。")
    neg = analyze_sentiment("法人不看好後市。")
    assert pos > 0
    assert neg < 0


def test_intensifier_amplifies():
    base = analyze_sentiment("股價下跌。")
    strong = analyze_sentiment("股價大幅下跌。")
    assert strong <= base  # 更負（或相等於飽和邊界）
    assert strong < 0


def test_score_bounded():
    s = analyze_sentiment("漲停大漲創高看好樂觀調升上修飆強勁亮眼突破" * 5)
    assert -1.0 <= s <= 1.0
    assert s == 1.0  # 飽和


def test_split_clauses():
    assert split_clauses("利多消息。股價大漲！外資買超？") == [
        "利多消息", "股價大漲", "外資買超",
    ]


def test_ticker_level_sentiment_isolates_clause():
    text = "台積電法說會樂觀，股價大漲；某生技公司新藥失敗，股價跌停。"
    tsmc = analyze_ticker_sentiment(text, ["台積電", "台積", "2330"])
    assert tsmc > 0  # 只看含「台積電」的子句 → 偏多


def test_ticker_sentiment_falls_back_to_doc():
    text = "大盤今日多方氣盛，類股全面走高，看好後市。"
    s = analyze_ticker_sentiment(text, ["台積電"], doc_fallback=0.5)
    assert s == 0.5  # 沒有子句明確提及 → 退回文件層級
