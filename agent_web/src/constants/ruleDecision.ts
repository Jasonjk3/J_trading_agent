/** 决策模式 */
export type DecisionMode = 'trader' | 'rule'

/** 规则组合策略（一期仅 priority_stack） */
export type RuleComposition = 'priority_stack'

export interface RuleCatalogItem {
  id: string
  name: string
  description: string
  defaultEnabled: boolean
}

/** 可启用的传统规则目录（与后端 decision/types.py 对齐） */
export const RULE_CATALOG: RuleCatalogItem[] = [
  { id: 'regime_detector', name: '市场状态识别', description: '自动判断趋势市 / 震荡市', defaultEnabled: true },
  { id: 'breakout', name: '突破追势', description: '价格突破近端高/低点且动能延续', defaultEnabled: true },
  { id: 'trend_follow', name: '趋势跟随', description: 'MA 排列 + MACD 柱体顺势参与', defaultEnabled: true },
  { id: 'bollinger_range', name: '布林震荡回归', description: '触及轨道上下沿后等待均值回归', defaultEnabled: true },
  { id: 'rsi_threshold', name: 'RSI 阈值', description: '震荡入场时的 RSI 超买超卖过滤', defaultEnabled: true },
  { id: 'volume_confirm', name: '成交量确认', description: '突破时要求放量确认', defaultEnabled: true },
  { id: 'trailing_stop', name: '跟踪止盈', description: '盈利达启动线后，回撤超阈值平仓', defaultEnabled: true },
  { id: 'fixed_pct_stop', name: '固定比例止盈止损', description: '按百分比止盈 / 止损', defaultEnabled: true },
  { id: 'ma_cross', name: '均线交叉', description: '持仓时 MA 反向交叉平仓', defaultEnabled: false },
]

export const DEFAULT_ENABLED_RULES = RULE_CATALOG.filter((r) => r.defaultEnabled).map((r) => r.id)

export interface RulePreset {
  id: string
  name: string
  description: string
  enabledRules: string[]
}

export const RULE_PRESETS: RulePreset[] = [
  {
    id: 'balanced_auto',
    name: '均衡自动',
    description: '趋势 + 震荡规则全集，适合大多数场景',
    enabledRules: [...DEFAULT_ENABLED_RULES],
  },
  {
    id: 'trend_rider',
    name: '纯趋势',
    description: '突破、趋势跟随与跟踪止盈',
    enabledRules: ['regime_detector', 'breakout', 'trend_follow', 'volume_confirm', 'trailing_stop', 'fixed_pct_stop'],
  },
  {
    id: 'range_scalper',
    name: '纯震荡',
    description: '布林回归 + RSI，适合区间行情',
    enabledRules: ['regime_detector', 'bollinger_range', 'rsi_threshold', 'fixed_pct_stop'],
  },
  {
    id: 'conservative',
    name: '保守',
    description: '较少规则、偏稳健出场',
    enabledRules: ['regime_detector', 'trend_follow', 'bollinger_range', 'trailing_stop', 'fixed_pct_stop'],
  },
  {
    id: 'custom',
    name: '自定义',
    description: '手动勾选启用规则',
    enabledRules: [...DEFAULT_ENABLED_RULES],
  },
]

export function resolveDecisionMode(cfg?: {
  decisionMode?: DecisionMode
} | null): DecisionMode {
  if (cfg?.decisionMode === 'trader' || cfg?.decisionMode === 'rule') return cfg.decisionMode
  return 'trader'
}

export function decisionModeLabel(mode: DecisionMode): string {
  return mode === 'rule' ? '规则策略' : 'AI 交易员'
}

export function resolveEnabledRules(ruleConfig?: {
  preset?: string
  enabledRules?: string[]
  disabledRules?: string[]
} | null): string[] {
  const preset = RULE_PRESETS.find((p) => p.id === ruleConfig?.preset)
  let enabled = ruleConfig?.enabledRules?.length
    ? [...ruleConfig.enabledRules]
    : preset
      ? [...preset.enabledRules]
      : [...DEFAULT_ENABLED_RULES]
  const disabled = new Set(ruleConfig?.disabledRules || [])
  enabled = enabled.filter((id) => !disabled.has(id))
  return enabled
}
