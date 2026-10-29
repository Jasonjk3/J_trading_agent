#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
持仓管理服务
"""
from app.v1.services.query_contracts import query_coverage, trading_sandbox_mode
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.inner_models.exchange_account_model import (
    ExchangeAccountModel,
    ExchangeCode,
    BindStatus
)
from app.v1.crud.exchange_account_crud import (
    get_exchange_accounts,
    get_exchange_account_by_id_and_user,
)
from app.v1.services.exchange_account_service import ExchangeAccountService
from app.v1.schemas.position_schema import (
    PositionListItem,
    PositionSummary,
    PositionSide,
    PositionHistoryItem,
    CloseType
)


class PositionService:
    """持仓管理服务"""
    
    def __init__(self):
        self._exchange_account_service = ExchangeAccountService()
    
    async def get_positions(
        self,
        session: AsyncSession,
        user_id: str,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int, Optional[Dict[str, str]]]:
        """
        获取用户持仓列表
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            exchange: 交易所筛选
            symbol: 交易对筛选
            side: 持仓方向筛选
            page: 页码
            page_size: 每页数量
            
        Returns:
            Tuple[持仓列表, 总数, 汇总信息]
        """
        exchange_enum = None
        if exchange:
            try:
                exchange_enum = ExchangeCode(exchange)
            except ValueError:
                raise ValueError("不支持的交易所") from None
        
        accounts = await get_exchange_accounts(
            session=session,
            user_id=user_id,
            exchange=exchange_enum,
            enabled=True,
            bind_status=BindStatus.SUCCESS
        )
        
        if not accounts:
            return [], 0, {"totalNotional": "0", "totalUnrealizedPnl": "0", **query_coverage(0, []), "warnings": ["未找到已启用且已验证的账户"]}
        
        failed = []
        all_positions: List[Dict[str, Any]] = []
        total_notional = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        
        for account in accounts:
            try:
                positions = await self._fetch_positions_from_exchange(account, symbol)
                for pos in positions:
                    if side and pos.get("side") != side:
                        continue
                    all_positions.append(pos)
                    
                    notional = Decimal(pos.get("notional", "0"))
                    unrealized_pnl = Decimal(pos.get("unrealizedPnl", "0"))
                    total_notional += notional
                    total_unrealized_pnl += unrealized_pnl
                    
            except Exception as e:
                failed.append(str(account.id))
                logger.error("交易所持仓查询失败: {}", type(e).__name__)
                continue
        
        total = len(all_positions)
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_positions = all_positions[start_idx:end_idx]
        
        summary = {
            "totalNotional": str(total_notional),
            "totalUnrealizedPnl": str(total_unrealized_pnl)
        }
        
        summary.update(query_coverage(len(accounts), failed))
        return paginated_positions, total, summary
    
    async def _fetch_positions_from_exchange(
        self,
        account: ExchangeAccountModel,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从交易所获取持仓数据
        
        Args:
            account: 交易所账户
            symbol: 交易对筛选
            
        Returns:
            持仓列表
        """
        api_key = self._exchange_account_service.decrypt(account.api_key)
        api_secret = self._exchange_account_service.decrypt(account.api_secret)
        passphrase = self._exchange_account_service.decrypt(account.passphrase) if account.passphrase else None
        
        if account.exchange == ExchangeCode.OKX:
            return await self._fetch_okx_positions(
                account_id=account.id,
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                symbol=symbol
            )
        
        raise ValueError("不支持的交易所")
    
    async def _fetch_okx_positions(
        self,
        account_id: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str],
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从OKX获取持仓数据
        
        Args:
            account_id: 账户ID
            api_key: API Key
            api_secret: API Secret
            passphrase: Passphrase
            symbol: 交易对筛选
            
        Returns:
            持仓列表
        """
        if not passphrase:
            raise ValueError("OKX账户缺少Passphrase")
        
        try:
            from lib.okx.okx_api import ApiService
            client = ApiService(
                API_KEY=api_key,
                SECRET_KEY=api_secret,
                PASSPHRASE=passphrase,
                IS_SANDBOX=trading_sandbox_mode(),
            )
            
            params = {}
            if symbol:
                params["inst_id"] = symbol
            
            okx_positions = await client.get_account_positions(**params)
            
            positions = []
            for pos in okx_positions:
                pos_data = pos if isinstance(pos, dict) else {}
                
                inst_id = pos_data.get("instId", "")
                pos_side = pos_data.get("posSide", "net")
                pos_qty = pos_data.get("pos", "0")
                
                if pos_qty == "0" or pos_qty == "":
                    continue
                
                side = self._convert_okx_pos_side(pos_side, pos_qty)
                
                avg_px = pos_data.get("avgPx", "0")
                mark_px = pos_data.get("markPx", "0")
                notional_usd = pos_data.get("notionalUsd", "0")
                upl = pos_data.get("upl", "0")
                upl_ratio = pos_data.get("uplRatio", "0")
                u_time = pos_data.get("uTime", "")
                
                upl_rate_percent = "0"
                if upl_ratio:
                    try:
                        upl_rate_percent = str(round(float(upl_ratio) * 100, 2))
                    except (ValueError, TypeError):
                        pass
                
                updated_at = None
                if u_time:
                    try:
                        timestamp_ms = int(u_time)
                        updated_at = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
                    except (ValueError, TypeError):
                        pass
                
                position_item = {
                    "id": f"{account_id}_{pos_data.get('posId', '')}",
                    "exchange": ExchangeCode.OKX.value,
                    "symbol": inst_id,
                    "side": side,
                    "quantity": str(abs(float(pos_qty))) if pos_qty else "0",
                    "costPrice": avg_px or "0",
                    "markPrice": mark_px or "0",
                    "notional": notional_usd or "0",
                    "unrealizedPnl": upl or "0",
                    "unrealizedPnlRate": upl_rate_percent,
                    "updatedAt": updated_at
                }
                positions.append(position_item)
            
            return positions
            
        except Exception as e:
            logger.error(f"获取OKX持仓失败: {e}")
            raise
    
    def _convert_okx_pos_side(self, pos_side: str, pos_qty: str) -> str:
        """
        转换OKX持仓方向到统一格式
        
        Args:
            pos_side: OKX返回的持仓方向 (long/short/net)
            pos_qty: 持仓数量（可能为负数表示空头）
            
        Returns:
            统一格式的持仓方向 (long/short)
        """
        if pos_side == "long":
            return PositionSide.LONG.value
        elif pos_side == "short":
            return PositionSide.SHORT.value
        elif pos_side == "net":
            try:
                qty = float(pos_qty)
                if qty > 0:
                    return PositionSide.LONG.value
                elif qty < 0:
                    return PositionSide.SHORT.value
                else:
                    return PositionSide.NET.value
            except (ValueError, TypeError):
                return PositionSide.NET.value
        else:
            return pos_side or PositionSide.NET.value

    async def get_positions_history(
        self,
        session: AsyncSession,
        user_id: str,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int, Optional[Dict[str, str]]]:
        """
        获取用户历史持仓列表
        
        Args:
            session: 数据库会话
            user_id: 用户ID
            exchange: 交易所筛选
            symbol: 交易对筛选
            side: 持仓方向筛选
            page: 页码
            page_size: 每页数量
            
        Returns:
            Tuple[历史持仓列表, 总数, 汇总信息]
        """
        exchange_enum = None
        if exchange:
            try:
                exchange_enum = ExchangeCode(exchange)
            except ValueError:
                raise ValueError("不支持的交易所") from None
        
        accounts = await get_exchange_accounts(
            session=session,
            user_id=user_id,
            exchange=exchange_enum,
            enabled=True,
            bind_status=BindStatus.SUCCESS
        )
        
        if not accounts:
            return [], 0, {"totalPnl": "0", **query_coverage(0, []), "warnings": ["未找到已启用且已验证的账户"]}
        
        failed = []
        all_history: List[Dict[str, Any]] = []
        total_pnl = Decimal("0")
        
        for account in accounts:
            try:
                history = await self._fetch_positions_history_from_exchange(account, symbol)
                for pos in history:
                    if side and pos.get("side") != side:
                        continue
                    all_history.append(pos)
                    
                    pnl = Decimal(pos.get("pnl", "0"))
                    total_pnl += pnl
                    
            except Exception as e:
                failed.append(str(account.id))
                logger.error("交易所历史持仓查询失败: {}", type(e).__name__)
                continue
        
        all_history.sort(key=lambda x: x.get("closeTime", "") or "", reverse=True)
        
        total = len(all_history)
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_history = all_history[start_idx:end_idx]
        
        summary = {
            "totalPnl": str(total_pnl)
        }
        
        summary.update(query_coverage(len(accounts), failed))
        return paginated_history, total, summary
    
    async def _fetch_positions_history_from_exchange(
        self,
        account: ExchangeAccountModel,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从交易所获取历史持仓数据
        
        Args:
            account: 交易所账户
            symbol: 交易对筛选
            
        Returns:
            历史持仓列表
        """
        api_key = self._exchange_account_service.decrypt(account.api_key)
        api_secret = self._exchange_account_service.decrypt(account.api_secret)
        passphrase = self._exchange_account_service.decrypt(account.passphrase) if account.passphrase else None
        
        if account.exchange == ExchangeCode.OKX:
            return await self._fetch_okx_positions_history(
                account_id=account.id,
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                symbol=symbol
            )
        
        raise ValueError("不支持的交易所")
    
    async def _fetch_okx_positions_history(
        self,
        account_id: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str],
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从OKX获取历史持仓数据
        
        Args:
            account_id: 账户ID
            api_key: API Key
            api_secret: API Secret
            passphrase: Passphrase
            symbol: 交易对筛选
            
        Returns:
            历史持仓列表
        """
        if not passphrase:
            raise ValueError("OKX账户缺少Passphrase")
        
        try:
            from lib.okx.okx_api import ApiService
            client = ApiService(
                API_KEY=api_key,
                SECRET_KEY=api_secret,
                PASSPHRASE=passphrase,
                IS_SANDBOX=trading_sandbox_mode(),
            )
            
            params = {}
            if symbol:
                params["inst_id"] = symbol
            
            okx_history = await client.get_positions_history(**params)
            
            history_list = []
            for pos in okx_history:
                pos_data = pos if isinstance(pos, dict) else {}
                
                inst_id = pos_data.get("instId", "")
                pos_side = pos_data.get("posSide", "net")
                direction = pos_data.get("direction", "")
                
                if direction == "long":
                    side = PositionSide.LONG.value
                elif direction == "short":
                    side = PositionSide.SHORT.value
                else:
                    side = self._convert_okx_pos_side(pos_side, pos_data.get("openMaxPos", "0"))
                
                open_avg_px = pos_data.get("openAvgPx", "0")
                close_avg_px = pos_data.get("closeAvgPx", "0")
                pnl = pos_data.get("pnl", "0")
                pnl_ratio = pos_data.get("pnlRatio", "0")
                lever = pos_data.get("lever", "1")
                close_type = pos_data.get("type", "")
                c_time = pos_data.get("cTime", "")
                close_time = pos_data.get("uTime", "")
                open_max_pos = pos_data.get("openMaxPos", "0")
                
                pnl_rate_percent = "0"
                if pnl_ratio:
                    try:
                        pnl_rate_percent = str(round(float(pnl_ratio) * 100, 2))
                    except (ValueError, TypeError):
                        pass
                
                open_time_str = None
                if c_time:
                    try:
                        timestamp_ms = int(c_time)
                        open_time_str = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
                    except (ValueError, TypeError):
                        pass
                
                close_time_str = None
                if close_time:
                    try:
                        timestamp_ms = int(close_time)
                        close_time_str = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
                    except (ValueError, TypeError):
                        pass
                
                close_type_mapped = self._convert_okx_close_type(close_type)
                
                history_item = {
                    "id": f"{account_id}_{pos_data.get('posId', '')}",
                    "exchange": ExchangeCode.OKX.value,
                    "symbol": inst_id,
                    "side": side,
                    "quantity": str(abs(float(open_max_pos))) if open_max_pos else "0",
                    "openAvgPrice": open_avg_px or "0",
                    "closeAvgPrice": close_avg_px or "0",
                    "pnl": pnl or "0",
                    "pnlRate": pnl_rate_percent,
                    "lever": lever or "1",
                    "closeType": close_type_mapped,
                    "openTime": open_time_str,
                    "closeTime": close_time_str
                }
                history_list.append(history_item)
            
            return history_list
            
        except Exception as e:
            logger.error(f"获取OKX历史持仓失败: {e}")
            raise
    
    def _convert_okx_close_type(self, okx_type: str) -> Optional[str]:
        """
        转换OKX平仓类型到统一格式
        
        Args:
            okx_type: OKX返回的平仓类型
            
        Returns:
            统一格式的平仓类型
        """
        type_mapping = {
            "1": CloseType.MANUAL.value,
            "2": CloseType.LIQUIDATION.value,
            "3": CloseType.PARTIAL_LIQUIDATION.value,
            "4": CloseType.ADL.value,
            "5": CloseType.DELIVERY.value,
            "liquidation": CloseType.LIQUIDATION.value,
            "partial_liquidation": CloseType.PARTIAL_LIQUIDATION.value,
            "adl": CloseType.ADL.value,
            "delivery": CloseType.DELIVERY.value,
            "manual": CloseType.MANUAL.value,
        }
        return type_mapping.get(okx_type, CloseType.MANUAL.value if okx_type else None)
