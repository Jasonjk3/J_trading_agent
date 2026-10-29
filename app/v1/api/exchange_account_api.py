#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
交易所账户管理API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from loguru import logger

from app.v1.schemas.exchange_account_schema import (
    CreateExchangeAccountRequest,
    UpdateExchangeAccountRequest,
)
from app.v1.services.exchange_account_service import ExchangeAccountService
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_user
from models.inner_models.user_model import UserModel
from models.inner_models.exchange_account_model import ExchangeCode, BindStatus

router = APIRouter(prefix="/exchange-accounts", tags=["交易所配置"])


def get_exchange_account_service() -> ExchangeAccountService:
    """获取交易所账户服务实例"""
    return ExchangeAccountService()


@router.get("", summary="获取交易所配置列表")
async def get_exchange_account_list(
    exchange: Optional[str] = Query(None, description="交易所标识"),
    enabled: Optional[bool] = Query(None, description="是否启用"),
    bindStatus: Optional[str] = Query(None, description="绑定状态"),
    session: AsyncSession = Depends(get_db_session),
    service: ExchangeAccountService = Depends(get_exchange_account_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取当前用户的交易所配置列表
    """
    try:
        exchange_enum = None
        if exchange:
            try:
                exchange_enum = ExchangeCode(exchange)
            except ValueError:
                return ApiResponse.failed_response(
                    msg=f"无效的交易所标识: {exchange}",
                    code=ResponseCode.FAILED.value
                )
        
        bind_status_enum = None
        if bindStatus:
            try:
                bind_status_enum = BindStatus(bindStatus)
            except ValueError:
                return ApiResponse.failed_response(
                    msg=f"无效的绑定状态: {bindStatus}",
                    code=ResponseCode.FAILED.value
                )
        
        accounts, total = await service.get_list(
            session=session,
            user_id=current_user.id,
            exchange=exchange_enum,
            enabled=enabled,
            bind_status=bind_status_enum
        )
        
        account_list = [service.model_to_response(account) for account in accounts]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "list": account_list,
                "total": total
            }
        )
    except Exception as e:
        logger.error(f"获取交易所配置列表失败: {e}")
        return ApiResponse.failed_response(
            msg="获取交易所配置列表失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("", summary="创建交易所配置")
async def create_exchange_account(
    request: CreateExchangeAccountRequest,
    session: AsyncSession = Depends(get_db_session),
    service: ExchangeAccountService = Depends(get_exchange_account_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    创建交易所配置
    """
    try:
        if request.exchange == ExchangeCode.OKX and not request.passphrase:
            return ApiResponse.failed_response(
                msg="OKX交易所需要提供Passphrase",
                code=ResponseCode.FAILED.value
            )
        
        account = await service.create(
            session=session,
            user_id=current_user.id,
            exchange=request.exchange,
            api_key=request.apiKey,
            api_secret=request.apiSecret,
            passphrase=request.passphrase,
            remark=request.remark,
            read_only=request.readOnly or False,
            enabled=request.enabled if request.enabled is not None else True
        )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=service.model_to_response(account)
        )
    except Exception as e:
        logger.error(f"创建交易所配置失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="创建交易所配置失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/{account_id}", summary="更新交易所配置")
async def update_exchange_account(
    account_id: str,
    request: UpdateExchangeAccountRequest,
    session: AsyncSession = Depends(get_db_session),
    service: ExchangeAccountService = Depends(get_exchange_account_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    更新交易所配置
    """
    try:
        account = await service.update(
            session=session,
            account_id=account_id,
            user_id=current_user.id,
            api_key=request.apiKey,
            api_secret=request.apiSecret,
            passphrase=request.passphrase,
            remark=request.remark,
            read_only=request.readOnly,
            enabled=request.enabled
        )
        
        if not account:
            return ApiResponse.failed_response(
                msg="交易所配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=service.model_to_response(account)
        )
    except Exception as e:
        logger.error(f"更新交易所配置失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="更新交易所配置失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/{account_id}", summary="删除交易所配置")
async def delete_exchange_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    service: ExchangeAccountService = Depends(get_exchange_account_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    删除交易所配置
    """
    try:
        success = await service.delete(
            session=session,
            account_id=account_id,
            user_id=current_user.id
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg="交易所配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        logger.error(f"删除交易所配置失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="删除交易所配置失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/{account_id}/verify", summary="校验交易所连接")
async def verify_exchange_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    service: ExchangeAccountService = Depends(get_exchange_account_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    校验交易所API连接
    """
    try:
        success, message = await service.verify(
            session=session,
            account_id=account_id,
            user_id=current_user.id
        )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="校验完成",
            data={
                "success": success,
                "message": message
            }
        )
    except Exception as e:
        logger.error(f"校验交易所连接失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="校验交易所连接失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )
