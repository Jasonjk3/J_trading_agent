#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析 Agent 测试脚本
"""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()


async def test_technical_analysis():
    """测试技术指标分析"""
    from agent_applications.task_agents.technical_analysis_agent import TechnicalAnalysisAgent
    
    print("=" * 60)
    print("技术指标分析 Agent 测试")
    print("=" * 60)
    
    agent = TechnicalAnalysisAgent(
        agent_name="测试技术分析Agent"
    )
    
    task = {
        "symbol": "BTC-USDT",
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "timeframe": "4h",
        "lookback_days": 30,
    }
    
    print(f"\n任务参数:")
    print(f"  - 交易对: {task['symbol']}")
    print(f"  - 分析日期: {task['analysis_date']}")
    print(f"  - K线周期: {task['timeframe']}")
    print(f"  - 回溯天数: {task['lookback_days']}")
    
    print("\n正在执行分析...")
    
    result = await agent.execute(task)
    
    print("\n" + "=" * 60)
    print("分析结果")
    print("=" * 60)
    
    if result.get("success"):
        print(f"\n✓ 分析成功")
        print(f"  - 交易对: {result.get('symbol')}")
        print(f"  - 分析日期: {result.get('analysis_date')}")
        print(f"  - 分析模式: {result.get('analysis_mode', 'llm')}")
        
        analysis = result.get("analysis", {})
        
        if analysis.get("summary"):
            print(f"\n【摘要】")
            print(f"  {analysis['summary']}")
        
        trend = analysis.get("trend", {})
        if trend:
            print(f"\n【趋势分析】")
            print(f"  - 方向: {trend.get('direction', 'N/A')}")
            print(f"  - 强度: {trend.get('strength', 'N/A')}")
            print(f"  - 描述: {trend.get('description', 'N/A')}")
        
        momentum = analysis.get("momentum", {})
        if momentum:
            print(f"\n【动量分析】")
            print(f"  - RSI状态: {momentum.get('rsi_status', 'N/A')}")
            print(f"  - MACD状态: {momentum.get('macd_status', 'N/A')}")
            print(f"  - 描述: {momentum.get('description', 'N/A')}")
        
        volatility = analysis.get("volatility", {})
        if volatility:
            print(f"\n【波动性分析】")
            print(f"  - 状态: {volatility.get('status', 'N/A')}")
            print(f"  - 布林带位置: {volatility.get('bollinger_position', 'N/A')}")
        
        signals = analysis.get("signals", [])
        if signals:
            print(f"\n【交易信号】")
            for sig in signals:
                print(f"  - [{sig.get('type', '')}] {sig.get('indicator', '')}: {sig.get('description', '')}")
        
        recommendation = analysis.get("recommendation", {})
        if recommendation:
            print(f"\n【交易建议】")
            print(f"  - 操作: {recommendation.get('action', 'N/A')}")
            print(f"  - 置信度: {recommendation.get('confidence', 'N/A')}")
            if recommendation.get('entry_zone'):
                print(f"  - 入场区间: {recommendation['entry_zone']}")
            if recommendation.get('stop_loss'):
                print(f"  - 止损位: {recommendation['stop_loss']}")
            if recommendation.get('take_profit'):
                print(f"  - 止盈位: {recommendation['take_profit']}")
            if recommendation.get('risk_warning'):
                print(f"  - 风险提示: {recommendation['risk_warning']}")
        
        indicators = result.get("raw_indicators", {})
        if indicators:
            print(f"\n【原始指标数据】")
            print(f"  - 当前价格: {indicators.get('current_price', 'N/A')}")
            print(f"  - MA5: {indicators.get('ma5', 'N/A')}")
            print(f"  - MA20: {indicators.get('ma20', 'N/A')}")
            print(f"  - RSI(14): {indicators.get('rsi_14', 'N/A')}")
            
            macd = indicators.get("macd", {})
            if macd:
                print(f"  - MACD DIF: {macd.get('dif', 'N/A')}")
                print(f"  - MACD DEA: {macd.get('dea', 'N/A')}")
            
            boll = indicators.get("bollinger", {})
            if boll:
                print(f"  - 布林上轨: {boll.get('upper', 'N/A')}")
                print(f"  - 布林中轨: {boll.get('middle', 'N/A')}")
                print(f"  - 布林下轨: {boll.get('lower', 'N/A')}")
    else:
        print(f"\n✗ 分析失败")
        print(f"  - 错误: {result.get('error', '未知错误')}")
    
    print("\n" + "=" * 60)


async def test_indicators_only():
    """仅测试指标计算（不调用LLM）"""
    from app.v1.services.technical_analysis_service import technical_analysis_service
    
    print("=" * 60)
    print("指标计算测试（无LLM）")
    print("=" * 60)
    
    result = await technical_analysis_service.get_indicators(
        symbol="ETH-USDT",
        timeframe="1h",
        lookback_days=14
    )
    
    if result.get("success"):
        print(f"\n✓ 获取成功")
        print(f"  - 交易对: {result.get('symbol')}")
        print(f"  - K线数量: {result.get('kline_count')}")
        
        indicators = result.get("indicators", {})
        print(f"\n【指标数据】")
        for key, value in indicators.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    - {k}: {v}")
            else:
                print(f"  - {key}: {value}")
    else:
        print(f"\n✗ 获取失败: {result.get('error')}")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print(" 技术指标分析 Agent 测试套件")
    print("=" * 60)
    
    print("\n[1/2] 测试完整分析流程...")
    await test_technical_analysis()
    
    print("\n[2/2] 测试指标计算...")
    await test_indicators_only()
    
    print("\n测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
