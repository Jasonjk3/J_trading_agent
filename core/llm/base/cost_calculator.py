#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
费用计算器
根据模型配置计算 LLM 调用费用
"""
import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ModelPricing:
    """模型定价配置"""
    model_name: str
    provider: str
    input_price_per_1m: float  # 每百万 token 输入价格（美元）
    output_price_per_1m: float  # 每百万 token 输出价格（美元）
    exchange_rate: float = 7.25  # 美元兑人民币汇率
    
    @property
    def input_price_per_1k(self) -> float:
        """每千 token 输入价格"""
        return self.input_price_per_1m / 1000
    
    @property
    def output_price_per_1k(self) -> float:
        """每千 token 输出价格"""
        return self.output_price_per_1m / 1000


# 默认价格配置（美元/百万 token）
DEFAULT_PRICING: Dict[str, ModelPricing] = {
    # DeepSeek 模型
    "deepseek-chat": ModelPricing(
        model_name="deepseek-chat",
        provider="deepseek",
        input_price_per_1m=0.14,
        output_price_per_1m=0.28,
    ),
    "deepseek-reasoner": ModelPricing(
        model_name="deepseek-reasoner",
        provider="deepseek",
        input_price_per_1m=0.55,
        output_price_per_1m=2.19,
    ),
    
    # OpenAI GPT-4 系列
    "gpt-4o": ModelPricing(
        model_name="gpt-4o",
        provider="openai",
        input_price_per_1m=2.50,
        output_price_per_1m=10.00,
    ),
    "gpt-4o-mini": ModelPricing(
        model_name="gpt-4o-mini",
        provider="openai",
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
    ),
    "gpt-4-turbo": ModelPricing(
        model_name="gpt-4-turbo",
        provider="openai",
        input_price_per_1m=10.00,
        output_price_per_1m=30.00,
    ),
    "gpt-4": ModelPricing(
        model_name="gpt-4",
        provider="openai",
        input_price_per_1m=30.00,
        output_price_per_1m=60.00,
    ),
    
    # OpenAI GPT-3.5 系列
    "gpt-3.5-turbo": ModelPricing(
        model_name="gpt-3.5-turbo",
        provider="openai",
        input_price_per_1m=0.50,
        output_price_per_1m=1.50,
    ),
    
    # OpenAI o1 系列
    "o1": ModelPricing(
        model_name="o1",
        provider="openai",
        input_price_per_1m=15.00,
        output_price_per_1m=60.00,
    ),
    # 注意：o1-mini 和 o1-preview 已于 2025 年被 OpenAI 弃用
    # "o1-mini": ModelPricing(...),  # 已弃用
    # "o1-preview": ModelPricing(...),  # 已弃用
    
    # OpenAI o3 系列
    "o3-mini": ModelPricing(
        model_name="o3-mini",
        provider="openai",
        input_price_per_1m=1.10,
        output_price_per_1m=4.40,
    ),
}


class CostCalculator:
    """
    费用计算器
    
    支持从数据库加载价格配置或使用默认配置
    """
    
    def __init__(
        self,
        default_exchange_rate: float = 7.25,
        custom_pricing: Optional[Dict[str, ModelPricing]] = None
    ):
        """
        初始化费用计算器
        
        Args:
            default_exchange_rate: 默认汇率
            custom_pricing: 自定义价格配置
        """
        self.default_exchange_rate = default_exchange_rate
        self._pricing_cache: Dict[str, ModelPricing] = {}
        
        # 合并默认配置和自定义配置
        self._pricing_cache.update(DEFAULT_PRICING)
        if custom_pricing:
            self._pricing_cache.update(custom_pricing)
    
    def get_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """
        获取模型定价配置
        
        Args:
            model_name: 模型名称
            
        Returns:
            ModelPricing 对象，如果未找到则返回 None
        """
        # 精确匹配
        if model_name in self._pricing_cache:
            return self._pricing_cache[model_name]
        
        # 模糊匹配（处理模型名称变体，如 gpt-4o-2024-01-01）
        for key, pricing in self._pricing_cache.items():
            if model_name.startswith(key):
                return pricing
        
        logger.warning(f"未找到模型 {model_name} 的价格配置，将使用零成本")
        return None
    
    def update_pricing(self, model_name: str, pricing: ModelPricing):
        """
        更新模型定价配置
        
        Args:
            model_name: 模型名称
            pricing: 定价配置
        """
        self._pricing_cache[model_name] = pricing
        logger.info(f"已更新模型 {model_name} 的价格配置")
    
    def update_pricing_from_db(
        self,
        model_name: str,
        provider: str,
        input_price_per_1m: float,
        output_price_per_1m: float,
        exchange_rate: float
    ):
        """
        从数据库配置更新定价
        
        Args:
            model_name: 模型名称
            provider: 提供商
            input_price_per_1m: 输入价格（$/1M tokens）
            output_price_per_1m: 输出价格（$/1M tokens）
            exchange_rate: 汇率
        """
        pricing = ModelPricing(
            model_name=model_name,
            provider=provider,
            input_price_per_1m=input_price_per_1m,
            output_price_per_1m=output_price_per_1m,
            exchange_rate=exchange_rate,
        )
        self.update_pricing(model_name, pricing)
    
    def remove_pricing(self, model_name: str):
        """
        移除模型定价配置（删除配置时调用）
        
        Args:
            model_name: 模型名称
        """
        if model_name in self._pricing_cache:
            del self._pricing_cache[model_name]
            logger.info(f"已移除模型 {model_name} 的价格配置")
    
    def calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model_name: str,
        exchange_rate: Optional[float] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        计算费用
        
        Args:
            prompt_tokens: 输入 token 数量
            completion_tokens: 输出 token 数量
            model_name: 模型名称
            exchange_rate: 汇率（如果为 None 则使用配置中的汇率）
            
        Returns:
            (cost_usd, cost_cny) 费用元组
        """
        pricing = self.get_pricing(model_name)
        
        if not pricing:
            return Decimal("0.000000"), Decimal("0.0000")
        
        # 计算美元费用
        # 公式：cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1,000,000
        input_cost = Decimal(str(prompt_tokens)) * Decimal(str(pricing.input_price_per_1m)) / Decimal("1000000")
        output_cost = Decimal(str(completion_tokens)) * Decimal(str(pricing.output_price_per_1m)) / Decimal("1000000")
        cost_usd = input_cost + output_cost
        
        # 四舍五入到 6 位小数
        cost_usd = cost_usd.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        
        # 计算人民币费用
        rate = exchange_rate if exchange_rate else pricing.exchange_rate
        cost_cny = cost_usd * Decimal(str(rate))
        cost_cny = cost_cny.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        
        return cost_usd, cost_cny
    
    def calculate_cost_detailed(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model_name: str,
        exchange_rate: Optional[float] = None
    ) -> Dict:
        """
        计算费用（详细信息）
        
        Args:
            prompt_tokens: 输入 token 数量
            completion_tokens: 输出 token 数量
            model_name: 模型名称
            exchange_rate: 汇率
            
        Returns:
            包含详细费用信息的字典
        """
        cost_usd, cost_cny = self.calculate_cost(
            prompt_tokens, completion_tokens, model_name, exchange_rate
        )
        
        pricing = self.get_pricing(model_name)
        rate = exchange_rate if exchange_rate else (pricing.exchange_rate if pricing else self.default_exchange_rate)
        
        return {
            "model_name": model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": float(cost_usd),
            "cost_cny": float(cost_cny),
            "exchange_rate": rate,
            "pricing": {
                "input_price_per_1m": pricing.input_price_per_1m if pricing else 0,
                "output_price_per_1m": pricing.output_price_per_1m if pricing else 0,
            } if pricing else None,
        }


# 全局单例实例
_cost_calculator: Optional[CostCalculator] = None


def get_cost_calculator() -> CostCalculator:
    """获取全局费用计算器实例"""
    global _cost_calculator
    if _cost_calculator is None:
        _cost_calculator = CostCalculator()
    return _cost_calculator


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str,
    exchange_rate: Optional[float] = None
) -> Tuple[Decimal, Decimal]:
    """
    便捷函数：计算费用
    
    Args:
        prompt_tokens: 输入 token 数量
        completion_tokens: 输出 token 数量
        model_name: 模型名称
        exchange_rate: 汇率
        
    Returns:
        (cost_usd, cost_cny) 费用元组
    """
    return get_cost_calculator().calculate_cost(
        prompt_tokens, completion_tokens, model_name, exchange_rate
    )


async def load_pricing_from_database() -> int:
    """
    从数据库加载生效的模型费用配置到 CostCalculator 缓存
    
    从 model_compare_model 表（公共模块模型管理）读取费用配置，统一费用数据源。
    应用启动时调用（API 网关、消费者等），确保内存中的价格配置与数据库同步。
    
    Returns:
        成功加载的配置数量
    """
    loaded = 0
    try:
        from configs.config import app_config
        from core.infrastructure.database.async_database import AsyncDatabase
        from sqlalchemy import select
        from models.inner_models.model_compare_model import ModelCompareModel
        
        async_db = AsyncDatabase(app_config)
        async with async_db.get_session() as session:
            # 从模型管理表读取启用的模型及其费用配置
            query = select(ModelCompareModel).where(ModelCompareModel.is_active == 1)
            result = await session.execute(query)
            models = result.scalars().all()
            
            calculator = get_cost_calculator()
            for model in models:
                # 只有设置了价格的模型才加载
                input_price = float(model.input_price_per_1m or 0)
                output_price = float(model.output_price_per_1m or 0)
                if input_price > 0 or output_price > 0:
                    calculator.update_pricing_from_db(
                        model_name=model.model_id,
                        provider=model.provider,
                        input_price_per_1m=input_price,
                        output_price_per_1m=output_price,
                        exchange_rate=7.25,  # 使用默认汇率
                    )
                    loaded += 1
        logger.info(f"已从 model_compare_model 表加载 {loaded} 条模型费用配置到 CostCalculator")
    except Exception as e:
        logger.warning(f"从数据库加载模型费用配置失败: {e}", exc_info=True)
    return loaded


def get_model_provider(model_name: str) -> str:
    """
    根据模型名称获取提供商
    
    Args:
        model_name: 模型名称
        
    Returns:
        提供商名称
    """
    pricing = get_cost_calculator().get_pricing(model_name)
    if pricing:
        return pricing.provider
    
    # 根据模型名称推断提供商
    model_lower = model_name.lower()
    if "deepseek" in model_lower:
        return "deepseek"
    elif "gpt" in model_lower or model_lower.startswith("o1"):
        return "openai"
    elif "claude" in model_lower:
        return "anthropic"
    elif "gemini" in model_lower:
        return "google"
    else:
        return "unknown"
