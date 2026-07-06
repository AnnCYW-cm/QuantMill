# -*- coding: utf-8 -*-
"""
schedule.py —— 让前瞻记录每天自动推进 | auto-advance the forward track daily
=====================================================================
macOS 用 launchd(睡眠错过会在下次唤醒补跑),其它系统给出 cron 一行。
纯生成器(build_launchd_plist / build_cron_line / parse_hhmm)可离线测;
真正 load/unload 才碰 subprocess。因 step_forward 按天幂等,调度不必卡点精确。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys

LABEL = "com.quantmill.forward"


def parse_hhmm(s: str) -> tuple:
    """'16:40' -> (16, 40),越界即报错。"""
    h, m = (int(x) for x in s.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"时间非法:{s}(应为 00:00~23:59)")
    return h, m


def plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def quantmill_bin() -> str:
    """定位 quantmill 可执行文件(优先与当前 python 同目录)。"""
    cand = os.path.join(os.path.dirname(sys.executable), "quantmill")
    return cand if os.path.exists(cand) else "quantmill"


def build_launchd_plist(markets, model, hh, mm, bin_path, workdir, log_path) -> str:
    args = [bin_path, "forward", "tick", "--markets", ",".join(markets), "--model", model]
    arg_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        f"  <key>Label</key><string>{LABEL}</string>\n"
        "  <key>ProgramArguments</key><array>\n"
        f"{arg_xml}\n"
        "  </array>\n"
        "  <key>StartCalendarInterval</key><dict>"
        f"<key>Hour</key><integer>{hh}</integer>"
        f"<key>Minute</key><integer>{mm}</integer></dict>\n"
        f"  <key>WorkingDirectory</key><string>{workdir}</string>\n"
        f"  <key>StandardOutPath</key><string>{log_path}</string>\n"
        f"  <key>StandardErrorPath</key><string>{log_path}</string>\n"
        "  <key>RunAtLoad</key><false/>\n"
        "</dict></plist>\n"
    )


def build_cron_line(markets, model, hh, mm, bin_path, workdir, log_path) -> str:
    cmd = (f"cd {workdir} && {bin_path} forward tick "
           f"--markets {','.join(markets)} --model {model} >> {log_path} 2>&1")
    return f"{mm} {hh} * * 1-5 {cmd}"          # 工作日(周一~周五)


def install(markets, model, at, workdir, log_path) -> dict:
    """安装每日自动推进。macOS→launchd;其它→返回 cron 指引(不擅自改 crontab)。"""
    hh, mm = parse_hhmm(at)
    bin_path = quantmill_bin()
    if platform.system() == "Darwin":
        p = plist_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(build_launchd_plist(markets, model, hh, mm, bin_path, workdir, log_path))
        subprocess.run(["launchctl", "unload", p], capture_output=True)   # 幂等:先卸再装
        r = subprocess.run(["launchctl", "load", p], capture_output=True, text=True)
        ok = r.returncode == 0
        return {"backend": "launchd", "ok": ok, "path": p,
                "err": r.stderr.strip(), "at": at, "markets": markets, "model": model}
    line = build_cron_line(markets, model, hh, mm, bin_path, workdir, log_path)
    return {"backend": "cron", "ok": False, "cron_line": line,
            "at": at, "markets": markets, "model": model}


def uninstall() -> dict:
    if platform.system() == "Darwin":
        p = plist_path()
        subprocess.run(["launchctl", "unload", p], capture_output=True)
        existed = os.path.exists(p)
        if existed:
            os.remove(p)
        return {"backend": "launchd", "removed": existed, "path": p}
    return {"backend": "cron", "removed": False,
            "note": "请手动 `crontab -e` 删掉含 'forward tick' 的那一行。"}


def is_installed() -> bool:
    return platform.system() == "Darwin" and os.path.exists(plist_path())
