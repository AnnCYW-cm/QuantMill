# -*- coding: utf-8 -*-
"""前瞻自动推进调度测试 —— 纯生成器离线锁死(不碰 launchctl/cron)。"""
import pytest

from quantmill.paper.schedule import (LABEL, build_cron_line,
                                      build_launchd_plist, parse_hhmm)


def test_parse_hhmm_ok():
    assert parse_hhmm("16:40") == (16, 40)
    assert parse_hhmm("0:0") == (0, 0)
    assert parse_hhmm("23:59") == (23, 59)


@pytest.mark.parametrize("bad", ["24:00", "12:60", "-1:00", "9"])
def test_parse_hhmm_rejects_bad(bad):
    with pytest.raises((ValueError, IndexError)):
        parse_hhmm(bad)


def test_launchd_plist_has_schedule_and_args():
    p = build_launchd_plist(["cn", "hk"], "composite", 16, 40,
                            "/x/quantmill", "/home/q", "/home/q/f.log")
    assert LABEL in p
    assert "<key>Hour</key><integer>16</integer>" in p
    assert "<key>Minute</key><integer>40</integer>" in p
    assert "<string>forward</string>" in p and "<string>tick</string>" in p
    assert "<string>cn,hk</string>" in p          # 多市场逗号拼进参数
    assert "<string>composite</string>" in p
    assert p.startswith("<?xml")                   # 合法 plist 头


def test_cron_line_weekdays_and_cmd():
    line = build_cron_line(["cn"], "ml", 16, 40,
                           "/x/quantmill", "/home/q", "/home/q/f.log")
    assert line.startswith("40 16 * * 1-5 ")       # 分 时 * * 工作日
    assert "forward tick --markets cn --model ml" in line
    assert ">> /home/q/f.log 2>&1" in line
