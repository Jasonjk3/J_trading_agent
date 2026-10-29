#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
初始化管理员账号脚本
用于创建系统初始管理员账号

使用方法：
    python scripts/init_admin_user.py

环境变量配置：
    MYSQL_HOST: MySQL主机地址（默认：127.0.0.1）
    MYSQL_PORT: MySQL端口（默认：3306）
    MYSQL_USERNAME: MySQL用户名
    MYSQL_PASSWORD: MySQL密码
    MYSQL_DB: 数据库名
    ADMIN_USERNAME: 管理员用户名（默认：admin）
    ADMIN_PASSWORD: 管理员密码（默认：admin123）
    ADMIN_EMAIL: 管理员邮箱（可选）
"""
import asyncio
import sys
import os
import uuid
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from passlib.context import CryptContext
from datetime import datetime

from models.inner_models.user_model import UserModel, UserRole
from configs.config import app_config

def get_password_hash(password: str) -> str:
    """获取密码哈希 - 使用 bcrypt 直接加密"""
    import bcrypt
    
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
    else:
        password_bytes = password
    
    # bcrypt 限制：密码不能超过72字节
    if len(password_bytes) > 72:
        print(f"⚠️  警告: 密码长度超过72字节，将被截断")
        password_bytes = password_bytes[:72]
    
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


async def create_admin_user():
    """创建管理员账号"""
    # 从环境变量或配置获取数据库信息
    mysql_host = os.getenv("MYSQL_HOST", app_config.MYSQL_HOST)
    mysql_port = os.getenv("MYSQL_PORT", str(app_config.MYSQL_PORT))
    mysql_username = os.getenv("MYSQL_USERNAME", app_config.MYSQL_USERNAME)
    mysql_password = os.getenv("MYSQL_PASSWORD", app_config.MYSQL_PASSWORD)
    mysql_db = os.getenv("MYSQL_DB", app_config.MYSQL_DB)
    
    # 管理员账号信息
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    admin_email = os.getenv("ADMIN_EMAIL", None)
    
    # 创建数据库连接
    db_url = (
        f"mysql+aiomysql://{mysql_username}:{mysql_password}"
        f"@{mysql_host}:{mysql_port}/{mysql_db}"
        f"?charset=utf8mb4"
    )
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    try:
        async with async_session() as session:
            # 检查用户是否已存在
            result = await session.execute(
                select(UserModel).where(UserModel.username == admin_username)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                print(f"\n⚠️  用户 '{admin_username}' 已存在！")
                print(f"   用户ID: {existing_user.id}")
                print(f"   角色: {existing_user.role.value}")
                print(f"   状态: {'已激活' if existing_user.is_active else '已禁用'}")
                
                # 询问是否更新密码
                try:
                    update = input("\n是否更新密码？(y/N): ").strip().lower()
                    if update == 'y':
                        new_password = input("请输入新密码（留空使用默认密码 admin123）: ").strip()
                        if not new_password:
                            new_password = admin_password
                        
                        if len(new_password) < 6:
                            print("❌ 密码长度至少6位！")
                            return
                        
                        existing_user.password_hash = get_password_hash(new_password)
                        existing_user.updated_at = datetime.now()
                        await session.commit()
                        print(f"✅ 密码已更新！")
                    else:
                        print("已取消操作。")
                except (KeyboardInterrupt, EOFError):
                    print("\n已取消操作。")
                return
            
            # 验证密码长度
            if len(admin_password) < 6:
                print("❌ 密码长度至少6位！")
                return
            
            # 创建新管理员账号
            user_id = str(uuid.uuid4())
            password_hash = get_password_hash(admin_password)
            
            new_user = UserModel(
                id=user_id,
                username=admin_username,
                email=admin_email if admin_email else None,
                password_hash=password_hash,
                role=UserRole.ADMIN,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            session.add(new_user)
            await session.commit()
            
            print("=" * 60)
            print("✅ 管理员账号创建成功！")
            print("=" * 60)
            print(f"用户名: {admin_username}")
            if admin_email:
                print(f"邮箱: {admin_email}")
            print(f"密码: {admin_password}")
            print(f"角色: 管理员 (admin)")
            print(f"用户ID: {user_id}")
            print("=" * 60)
            print("⚠️  重要提示：")
            print("   1. 请妥善保管管理员账号信息")
            print("   2. 首次登录后请立即修改密码")
            print("   3. 建议在生产环境中使用强密码")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 创建管理员账号失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print("正在初始化管理员账号...")
    asyncio.run(create_admin_user())
