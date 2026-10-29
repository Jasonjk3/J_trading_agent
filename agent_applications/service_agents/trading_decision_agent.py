"""交易决策兼容入口。

旧 LLM 决策器及其评分/信号 guardrail 已废弃。运行实现位于 ``trader.agent``。
保留模块路径和类名，仅用于兼容现有回测、实盘调度和外部导入。
"""

from trader.agent import TraderAgent


TradingDecisionAgent = TraderAgent

__all__ = ["TradingDecisionAgent", "TraderAgent"]
