# -*- coding: utf-8 -*-
"""test_watchlist.py —— 自选股清单解析 | watchlist parsing"""

from quantmill.watchlist import load_watchlist
from quantmill.report.dashboard import _signal


def test_load_watchlist_parses_and_skips_invalid(tmp_path):
    """注释/空行忽略;非法市场、格式错的行跳过;两种写法都支持。
    Comments/blank lines ignored; invalid market and malformed lines skipped; both syntaxes work."""
    f = tmp_path / "wl.txt"
    f.write_text(
        "# 注释行\n"
        "\n"
        "us AAPL\n"
        "us:MSFT\n"          # 冒号写法 | colon syntax
        "hk 00700\n"
        "xx 12345\n"          # 非法市场 -> 跳过 | invalid market -> skip
        "us\n"                # 缺代码 -> 跳过 | missing code -> skip
        "cn 600519\n",
        encoding="utf-8",
    )
    wl = load_watchlist(str(f))
    assert wl == {"us": ["AAPL", "MSFT"], "hk": ["00700"], "cn": ["600519"]}
    assert "xx" not in wl


def test_load_watchlist_autocreates_when_missing(tmp_path):
    """文件不存在时自动生成默认清单,并能读回非空内容。
    Auto-generate a default watchlist when missing, and read back non-empty content."""
    f = tmp_path / "new_wl.txt"
    assert not f.exists()
    wl = load_watchlist(str(f))
    assert f.exists()                                 # 已生成 | created
    assert sum(len(v) for v in wl.values()) > 0       # 非空 | non-empty


def test_signal_thresholds():
    """信号阈值映射:高->持有,低->空仓,中间->观望。
    Signal mapping: high -> hold, low -> cash, middle -> wait."""
    assert "持有" in _signal(0.70, buy_th=0.55, sell_th=0.45)
    assert "空仓" in _signal(0.30, buy_th=0.55, sell_th=0.45)
    assert "观望" in _signal(0.50, buy_th=0.55, sell_th=0.45)
