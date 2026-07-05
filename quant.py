# -*- coding: utf-8 -*-
"""
quant.py —— 统一命令入口(薄壳,逻辑在 quantmill/cli.py)
quant.py —— Unified command entry (thin shim; logic lives in quantmill/cli.py)
============================================================================
本地直接跑 | Run locally:
    ./.venv/bin/python quant.py scan | validate | analyze AAPL us | home

装成包后可直接用 `quant ...` | After `pip install -e .`, just use `quant ...`.
"""

from quantmill.workflow.cli import main

if __name__ == "__main__":
    main()
