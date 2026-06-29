from stock_heat.processing.dictionary import get_dictionary
from stock_heat.processing.ticker_recognition import recognize_tickers

DICT = get_dictionary("data/tickers.csv")


def _tickers(text: str) -> dict[str, float]:
    return {r.ticker: r.confidence for r in recognize_tickers(text, DICT)}


def test_official_name_passes_threshold():
    res = _tickers("台積電法說會釋出樂觀展望，外資調升目標價。")
    assert "2330" in res
    assert res["2330"] >= 0.5


def test_code_with_context_recognized():
    res = _tickers("個股 2330 今日股價走高，成交量放大。")
    assert "2330" in res
    assert res["2330"] >= 0.6  # 代號 + 上下文


def test_bare_number_without_context_not_recognized():
    # 2317 出現但無任何股市上下文、也無名稱/別名 → 單一裸代號 0.4 < 0.5
    res = _tickers("這款產品售價 2317 元，CP 值很高。")
    assert "2317" not in res


def test_longest_match_disambiguation():
    # 「中華電信」應歸 2412，不應因內含「中華」而誤判到 2204
    res = _tickers("中華電信看好5G營收成長，法人調升目標價。")
    assert "2412" in res
    assert "2204" not in res


def test_name_plus_code_boosts_confidence():
    res = _tickers("台積電（2330）法說會看好，外資買超。")
    assert res["2330"] >= 0.6  # 名稱(0.5)+代號(0.6) → base 0.6 + 加成


def test_multiple_tickers_in_one_text():
    res = _tickers("台積電與聯發科同步走高，長榮海運則因運價回升受惠。")
    assert {"2330", "2454", "2603"}.issubset(res.keys())


def test_empty_text_returns_nothing():
    assert recognize_tickers("", DICT) == []
