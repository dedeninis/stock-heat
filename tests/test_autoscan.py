import threading

from stock_heat.autoscan import _loop, enabled, scan_interval, start_autoscan


def test_loop_runs_then_stops():
    calls = []
    stop = threading.Event()

    def runner():
        calls.append(1)
        stop.set()  # 第一輪後即停

    _loop(0, runner, stop)
    assert len(calls) == 1


def test_loop_survives_runner_exception():
    calls = []
    stop = threading.Event()

    def runner():
        calls.append(1)
        stop.set()
        raise RuntimeError("boom")

    _loop(0, runner, stop)  # 例外不應外漏
    assert len(calls) == 1


def test_start_autoscan_invokes_runner():
    calls = []
    stop = threading.Event()

    def runner():
        calls.append(1)
        stop.set()

    t = start_autoscan(interval=0, runner=runner, stop=stop)
    t.join(timeout=3)
    assert not t.is_alive()
    assert calls


def test_scan_interval_default(monkeypatch):
    monkeypatch.delenv("STOCKHEAT_SCAN_INTERVAL", raising=False)
    assert scan_interval() == 1800


def test_scan_interval_clamped_and_env(monkeypatch):
    monkeypatch.setenv("STOCKHEAT_SCAN_INTERVAL", "10")
    assert scan_interval() == 60  # 下限 60
    monkeypatch.setenv("STOCKHEAT_SCAN_INTERVAL", "300")
    assert scan_interval() == 300


def test_enabled_flag(monkeypatch):
    monkeypatch.delenv("STOCKHEAT_AUTO_SCAN", raising=False)
    assert enabled() is False
    monkeypatch.setenv("STOCKHEAT_AUTO_SCAN", "1")
    assert enabled() is True
