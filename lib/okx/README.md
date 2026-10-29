# OKX API V5 永续合约交易接口

本模块提供了完整的OKX API V5永续合约交易功能，包括做多、做空、杠杆设置、止盈止损等高级交易功能。

## 功能特性

### 1. 基础交易功能
- ✅ 永续合约下单（市价单、限价单）
- ✅ 批量下单
- ✅ 撤销订单
- ✅ 批量撤销订单
- ✅ 查询订单信息
- ✅ 查询未成交订单
- ✅ 查询历史订单
- ✅ 查询成交明细

### 2. 做多/做空功能
- ✅ 开多仓（long position）
- ✅ 开空仓（short position）
- ✅ 平仓功能
- ✅ 持仓方向管理

### 3. 杠杆设置
- ✅ 设置杠杆倍数
- ✅ 查询当前杠杆设置
- ✅ 支持全仓/逐仓模式

### 4. 止盈止损
- ✅ 单向止盈止损
- ✅ 双向止盈止损
- ✅ 移动止盈
- ✅ 策略委托订单管理

### 5. 风险控制
- ✅ 账户余额查询
- ✅ 持仓信息查询
- ✅ 风险比例计算
- ✅ 强平风险预警

## 文件结构

```
backend/lib/okx/
├── api.py                 # 核心API接口类
├── okx_base.py           # 基础类，处理签名和请求
├── trading_service.py    # 高级交易服务类
├── trading_example.py    # 使用示例
├── utils.py              # 工具函数
└── README.md             # 说明文档
```

## 快速开始

### 1. 基础使用

```python
from backend.lib.okx.okx_api import ApiService

# 初始化API服务
api = ApiService(
    API_KEY="your_api_key",
    SECRET_KEY="your_secret_key",
    PASSPHRASE="your_passphrase",
    IS_SANDBOX=True  # 使用沙盒环境
)

# 获取市场信息
ticker = await api.get_ticker("BTC-USDT-SWAP")
print(f"BTC价格: {ticker['last']}")

# 下单（做多）
order = await api.place_order(
    inst_id="BTC-USDT-SWAP",
    td_mode="cross",  # 全仓模式
    side="buy",  # 买入
    ord_type="market",  # 市价单
    sz="0.001",  # 数量
    pos_side="long"  # 开多
)
```

### 2. 使用交易服务类

```python
from backend.lib.okx.okx_trading_service import OkxTradingService

# 创建交易服务
trading = OkxTradingService(
    api_key="your_api_key",
    secret_key="your_secret_key",
    passphrase="your_passphrase",
    is_sandbox=True
)

# 初始化交易设置
await trading.initialize_trading("BTC-USDT-SWAP", "10", "cross")

# 开多仓（100美元）
await trading.open_long_position(100.0)

# 开空仓（100美元，限价单）
current_price = await trading.get_market_price()
await trading.open_short_position(100.0, current_price * 0.95, "limit")

# 设置止盈止损
await trading.set_take_profit_stop_loss(
    pos_side="long",
    tp_price=current_price * 1.05,  # 止盈5%
    sl_price=current_price * 0.95  # 止损5%
)
```

### 3. 风险控制

```python
# 获取账户摘要
summary = await trading.get_account_summary()
print(f"总权益: ${summary['total_equity']:.2f}")
print(f"未实现盈亏: ${summary['total_upl']:.2f}")

# 风险检查
risk_info = await trading.risk_management_check()
print(f"风险比例: {risk_info['risk_ratio']:.2%}")
print(f"风险建议: {risk_info['recommendation']}")

# 获取持仓信息
positions = await trading.get_position_info()
for pos in positions:
    print(f"持仓方向: {pos['posSide']}")
    print(f"持仓数量: {pos['pos']}")
    print(f"未实现盈亏: {pos['upl']}")
```

## API接口说明

### 核心交易接口

#### 1. 下单接口
```python
async def place_order(self, inst_id: str, td_mode: str, side: str, ord_type: str,
                     sz: str, px: str = None, pos_side: str = None, ...) -> Dict:
    """下单
    
    Args:
        inst_id: 产品ID，如 "BTC-USDT-SWAP"
        td_mode: 交易模式 (cash/cross/isolated)
        side: 订单方向 (buy/sell)
        ord_type: 订单类型 (market/limit/post_only/fok/ioc)
        sz: 委托数量
        px: 委托价格（限价单必填）
        pos_side: 持仓方向 (long/short/net)
        ...
    """
```

#### 2. 杠杆设置
```python
async def set_leverage(self, inst_id: str, lever: str, mgn_mode: str, 
                      pos_side: str = None, ccy: str = None) -> Dict:
    """设置杠杆倍数
    
    Args:
        inst_id: 产品ID
        lever: 杠杆倍数
        mgn_mode: 保证金模式 (cross/isolated)
        pos_side: 持仓方向 (long/short/net)
        ccy: 保证金币种
    """
```

#### 3. 止盈止损
```python
async def place_algo_order(self, inst_id: str, td_mode: str, side: str, ord_type: str,
                          sz: str, tp_trigger_px: str = None, sl_trigger_px: str = None, ...) -> Dict:
    """下止盈止损单
    
    Args:
        inst_id: 产品ID
        td_mode: 交易模式
        side: 订单方向
        ord_type: 订单类型 (conditional/oco/trigger/ice/twap)
        sz: 委托数量
        tp_trigger_px: 止盈触发价
        sl_trigger_px: 止损触发价
        ...
    """
```

### 查询接口

#### 1. 市场数据
- `get_ticker()` - 获取单个产品行情
- `get_market_depth()` - 获取市场深度
- `get_tickers()` - 获取所有产品行情
- `get_candlesticks()` - 获取K线数据

#### 2. 账户信息
- `get_account_balance()` - 获取账户余额
- `get_account_positions()` - 获取持仓信息
- `get_positions_history()` - 获取历史持仓

#### 3. 订单管理
- `get_order()` - 获取单个订单信息
- `get_orders_pending()` - 获取未成交订单
- `get_orders_history()` - 获取历史订单
- `get_fills()` - 获取成交明细

## 交易模式说明

### 1. 交易模式 (td_mode)
- `cash`: 现金模式
- `cross`: 全仓模式（推荐）
- `isolated`: 逐仓模式

### 2. 持仓方向 (pos_side)
- `long`: 开多/多头
- `short`: 开空/空头
- `net`: 单向持仓

### 3. 订单类型 (ord_type)
- `market`: 市价单
- `limit`: 限价单
- `post_only`: 只做maker单
- `fok`: 全部成交或立即取消
- `ioc`: 立即成交并取消剩余

### 4. 策略委托类型
- `conditional`: 单向止盈止损
- `oco`: 双向止盈止损
- `trigger`: 移动止盈
- `ice`: 冰山委托
- `twap`: 时间加权委托

## 风险提示

1. **测试环境**: 建议先在沙盒环境测试所有功能
2. **资金管理**: 合理控制仓位大小，避免过度杠杆
3. **止损设置**: 建议设置合理的止损价格
4. **风险监控**: 定期检查风险比例和强平价格
5. **API限制**: 注意API调用频率限制

## 错误处理

所有接口都包含完整的错误处理机制：

```python
try:
    result = await api.place_order(...)
    print("下单成功:", result)
except Exception as e:
    print(f"下单失败: {e}")
```

## 示例代码

完整的使用示例请参考：
- `trading_example.py` - 基础使用示例
- `trading_service.py` - 高级交易服务示例

## 注意事项

1. 请确保API密钥的安全性
2. 生产环境请关闭调试输出
3. 建议实现完整的日志记录
4. 定期更新API版本
5. 遵守交易所规则和法律法规

## 更新日志

- 2025-03-07: 初始版本，实现基础交易功能
- 支持永续合约交易
- 支持做多/做空功能
- 支持杠杆设置
- 支持止盈止损
- 支持风险控制
