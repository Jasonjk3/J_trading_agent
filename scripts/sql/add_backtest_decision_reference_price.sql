-- 决策记录：决策时点参考价（与 API currentPrice 对应）
ALTER TABLE backtest_decisions
  ADD COLUMN reference_price DECIMAL(20, 8) NULL COMMENT '决策时点该交易对参考价' AFTER chain_of_thought;
