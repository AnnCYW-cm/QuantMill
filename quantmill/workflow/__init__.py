"""
workflow —— 编排层 | Orchestration layer
=========================================
把各层串成端到端流水线并对外暴露命令。
  pipeline  单标的完整流程(数据→特征→模型→回测→报告)
  cli       统一命令入口(scan / validate / analyze / home)
Chains layers into end-to-end pipelines and exposes the CLI.
(未来:配置驱动的 YAML 工作流 | future: config-driven YAML workflows)
"""

from quantmill.workflow.pipeline import run_single

__all__ = ["run_single"]
