#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
交易所账户服务
"""
import base64
import hashlib
import hmac
from datetime import datetime
from typing import Optional, List, Tuple
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
    create_exchange_account,
    update_exchange_account,
    delete_exchange_account,
    update_bind_status,
    count_exchange_accounts
)
from configs.config import settings


class SimpleEncryptor:
    """简单的加密器，使用 XOR 和 base64"""
    
    def __init__(self, key: str):
        self.key = hashlib.sha256(key.encode()).digest()
    
    def encrypt(self, data: str) -> str:
        """加密数据"""
        if not data:
            return data
        data_bytes = data.encode('utf-8')
        encrypted = bytes([data_bytes[i] ^ self.key[i % len(self.key)] for i in range(len(data_bytes))])
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')
    
    def decrypt(self, data: str) -> str:
        """解密数据"""
        if not data:
            return data
        try:
            encrypted = base64.urlsafe_b64decode(data.encode('utf-8'))
            decrypted = bytes([encrypted[i] ^ self.key[i % len(self.key)] for i in range(len(encrypted))])
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"解密失败: {e}")
            return data


class ExchangeAccountService:
    """交易所账户服务"""
    
    def __init__(self):
        self._encryptor = None
    
    @property
    def encryptor(self) -> SimpleEncryptor:
        """获取加密器实例"""
        if self._encryptor is None:
            key = getattr(settings.app_config, 'SECRET_KEY', 'default_secret_key_for_encryption')
            self._encryptor = SimpleEncryptor(key)
        return self._encryptor
    
    def encrypt(self, data: str) -> str:
        """加密数据"""
        return self.encryptor.encrypt(data)
    
    def decrypt(self, data: str) -> str:
        """解密数据"""
        return self.encryptor.decrypt(data)
    
    async def get_list(
        self,
        session: AsyncSession,
        user_id: str,
        exchange: Optional[ExchangeCode] = None,
        enabled: Optional[bool] = None,
        bind_status: Optional[BindStatus] = None
    ) -> Tuple[List[ExchangeAccountModel], int]:
        """获取交易所账户列表"""
        accounts = await get_exchange_accounts(
            session=session,
            user_id=user_id,
            exchange=exchange,
            enabled=enabled,
            bind_status=bind_status
        )
        total = await count_exchange_accounts(
            session=session,
            user_id=user_id,
            exchange=exchange,
            enabled=enabled,
            bind_status=bind_status
        )
        return accounts, total
    
    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        exchange: ExchangeCode,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
        remark: Optional[str] = None,
        read_only: bool = False,
        enabled: bool = True
    ) -> ExchangeAccountModel:
        """创建交易所账户"""
        encrypted_api_key = self.encrypt(api_key)
        encrypted_api_secret = self.encrypt(api_secret)
        encrypted_passphrase = self.encrypt(passphrase) if passphrase else None
        
        account = await create_exchange_account(
            session=session,
            user_id=user_id,
            exchange=exchange,
            api_key=encrypted_api_key,
            api_secret=encrypted_api_secret,
            passphrase=encrypted_passphrase,
            remark=remark,
            read_only=read_only,
            enabled=enabled
        )
        return account
    
    async def update(
        self,
        session: AsyncSession,
        account_id: str,
        user_id: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        remark: Optional[str] = None,
        read_only: Optional[bool] = None,
        enabled: Optional[bool] = None
    ) -> Optional[ExchangeAccountModel]:
        """更新交易所账户"""
        account = await get_exchange_account_by_id_and_user(session, account_id, user_id)
        if not account:
            return None
        
        update_data = {}
        if api_key is not None:
            update_data['api_key'] = self.encrypt(api_key)
        if api_secret is not None:
            update_data['api_secret'] = self.encrypt(api_secret)
        if passphrase is not None:
            update_data['passphrase'] = self.encrypt(passphrase) if passphrase else None
        if remark is not None:
            update_data['remark'] = remark
        if read_only is not None:
            update_data['read_only'] = read_only
        if enabled is not None:
            update_data['enabled'] = enabled
        
        if not update_data:
            return account
        
        return await update_exchange_account(session, account_id, update_data)
    
    async def delete(
        self,
        session: AsyncSession,
        account_id: str,
        user_id: str
    ) -> bool:
        """删除交易所账户"""
        account = await get_exchange_account_by_id_and_user(session, account_id, user_id)
        if not account:
            return False
        return await delete_exchange_account(session, account_id)
    
    async def verify(
        self,
        session: AsyncSession,
        account_id: str,
        user_id: str
    ) -> Tuple[bool, str]:
        """验证交易所账户连接"""
        account = await get_exchange_account_by_id_and_user(session, account_id, user_id)
        if not account:
            return False, "账户不存在"
        
        api_key = self.decrypt(account.api_key)
        api_secret = self.decrypt(account.api_secret)
        passphrase = self.decrypt(account.passphrase) if account.passphrase else None
        
        try:
            success, message = await self._verify_okx(api_key, api_secret, passphrase)
            
            new_status = BindStatus.SUCCESS if success else BindStatus.FAILED
            await update_bind_status(
                session=session,
                account_id=account_id,
                bind_status=new_status,
                verified_at=datetime.now()
            )
            
            return success, message
        except Exception as e:
            logger.error(f"验证交易所连接失败: {e}")
            await update_bind_status(
                session=session,
                account_id=account_id,
                bind_status=BindStatus.FAILED,
                verified_at=datetime.now()
            )
            return False, f"验证失败: {str(e)}"
    
    async def _verify_okx(
        self,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str]
    ) -> Tuple[bool, str]:
        """验证OKX连接"""
        if not passphrase:
            return False, "OKX需要提供Passphrase"
        
        try:
            from lib.okx.okx_api import ApiService
            client = ApiService(
                API_KEY=api_key,
                SECRET_KEY=api_secret,
                PASSPHRASE=passphrase
            )
            await client.get_account_balance()
            return True, "连接成功"
        except Exception as e:
            error_msg = str(e)
            logger.error(f"OKX验证失败: {error_msg}")
            if "Invalid API-Key" in error_msg or "50111" in error_msg:
                return False, "API Key无效"
            elif "Invalid Sign" in error_msg or "50113" in error_msg:
                return False, "签名无效，请检查API Secret"
            elif "Invalid Passphrase" in error_msg or "50114" in error_msg:
                return False, "Passphrase无效"
            elif "API Key权限不足" in error_msg:
                return False, "API Key权限不足"
            else:
                return False, f"验证失败: {error_msg}"
    
    def model_to_response(self, account: ExchangeAccountModel) -> dict:
        """将模型转换为响应格式"""
        return {
            "id": account.id,
            "exchange": account.exchange.value,
            "remark": account.remark,
            "bindStatus": account.bind_status.value,
            "lastVerifiedAt": account.last_verified_at.isoformat() if account.last_verified_at else None,
            "enabled": account.enabled,
            "readOnly": account.read_only,
            "apiKeyMasked": account.get_api_key_masked(),
            "hasPassphrase": account.has_passphrase,
            "createdAt": account.created_at.isoformat(),
            "updatedAt": account.updated_at.isoformat() if account.updated_at else None
        }
