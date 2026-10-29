#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
认证服务
处理用户认证、JWT Token生成和验证
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
import bcrypt
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from models.inner_models.user_model import UserModel, UserRole
from app.v1.crud.user_crud import (
    get_user_by_username,
    get_user_by_email,
    create_user
)
from configs.config import app_config


def _truncate_password_bytes(password: str, max_bytes: int = 72) -> bytes:
    """将密码转换为字节并安全截断到指定字节数"""
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
    else:
        password_bytes = password
    
    if len(password_bytes) > max_bytes:
        password_bytes = password_bytes[:max_bytes]
    
    return password_bytes

# JWT配置
SECRET_KEY = app_config.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7  # Token过期时间7天


class AuthService:
    """认证服务"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        if not hashed_password:
            logger.warning("密码哈希为空")
            return False
        
        if not isinstance(hashed_password, str):
            logger.warning(f"密码哈希类型错误: {type(hashed_password)}")
            return False
        
        if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
            logger.warning(f"密码哈希格式无效: {hashed_password[:20]}...")
            return False
        
        try:
            password_bytes = _truncate_password_bytes(plain_password)
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception as e:
            logger.error(f"密码验证失败: {e}, 哈希值: {hashed_password[:30]}...")
            return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        """获取密码哈希"""
        password_bytes = _truncate_password_bytes(password)
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')

    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            logger.warning(f"Token验证失败: {e}")
            return None

    async def authenticate_user(
        self,
        session: AsyncSession,
        username: str,
        password: str
    ) -> Optional[UserModel]:
        """验证用户身份"""
        user = await get_user_by_username(session, username)
        if not user:
            return None
        
        if not user.is_active:
            logger.warning(f"用户 {username} 已被禁用")
            return None
        
        # 检查密码哈希是否有效
        if not user.password_hash:
            logger.error(f"用户 {username} 的密码哈希为空")
            return None
        
        try:
            if not self.verify_password(password, user.password_hash):
                return None
        except Exception as e:
            logger.error(f"验证用户 {username} 密码时发生错误: {e}")
            logger.error(f"密码哈希值: {user.password_hash[:50] if user.password_hash else 'None'}...")
            # 如果密码哈希格式无效，返回 None（登录失败）
            return None
        
        return user

    async def login(
        self,
        session: AsyncSession,
        username: str,
        password: str
    ) -> Optional[Dict[str, Any]]:
        """用户登录"""
        user = await self.authenticate_user(session, username, password)
        if not user:
            return None
        
        # 创建Token
        access_token = self.create_access_token(
            data={"sub": user.id, "username": user.username, "role": user.role.value}
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active
            }
        }

    async def create_user_account(
        self,
        session: AsyncSession,
        username: str,
        password: str,
        email: Optional[str] = None,
        role: UserRole = UserRole.USER,
        is_active: bool = True
    ) -> UserModel:
        """创建用户账号（管理员操作）"""
        # 检查用户名是否已存在
        existing_user = await get_user_by_username(session, username)
        if existing_user:
            raise ValueError(f"用户名 {username} 已存在")
        
        # 检查邮箱是否已存在
        if email:
            existing_email = await get_user_by_email(session, email)
            if existing_email:
                raise ValueError(f"邮箱 {email} 已被使用")
        
        # 加密密码
        password_hash = self.get_password_hash(password)
        
        # 创建用户
        user = await create_user(
            session=session,
            username=username,
            password_hash=password_hash,
            email=email,
            role=role,
            is_active=is_active
        )
        
        await session.commit()
        return user

    async def reset_password(
        self,
        session: AsyncSession,
        username: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """重置密码"""
        user = await get_user_by_username(session, username)
        if not user:
            return False
        
        # 验证旧密码
        if not self.verify_password(old_password, user.password_hash):
            return False
        
        # 更新密码
        new_password_hash = self.get_password_hash(new_password)
        user.password_hash = new_password_hash
        user.updated_at = datetime.now()
        
        await session.commit()
        return True
