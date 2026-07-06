# -*- coding: utf-8 -*-
"""
paper —— 前瞻纸面记录 | forward paper track record
=====================================================================
投资经理的唯一硬要求:别再给我看回测,给我一条【不回看的前瞻曲线】。
本模块把"风控后的稳健组合"接成:每天跑一次 → 按当日真实价格标记市值 →
【只追加、绝不改历史】地记录净值 → 到换仓日才换成新目标。

这才是兑现平台立身之本(回测会骗人)的方式:用真实流逝的时间去证明它。
⚠️ 它只前进、不回测:历史点一旦写下就不再改(由测试锁死)。
"""
from __future__ import annotations

from quantmill.paper.forward import (forward_summary, load_state, run_forward,
                                     step_forward, target_weights)

__all__ = ["target_weights", "step_forward", "run_forward", "load_state", "forward_summary"]
