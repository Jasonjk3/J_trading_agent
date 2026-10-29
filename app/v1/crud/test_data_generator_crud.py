#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/27
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
测试数据生成器 CRUD 操作
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.test_data_generator_model import (
    TestDataConnection,
    TestDataOperationLog,
    TestDataInputHistory,
    ConnectionStatus,
    OperationType,
    OperationStatus,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 数据库连接 CRUD
# ============================================================================

async def get_connections(
    session: AsyncSession,
    user_id: str,
    is_active: Optional[bool] = True
) -> List[TestDataConnection]:
    """
    获取用户的数据库连接列表
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        is_active: 是否只返回启用的连接
        
    Returns:
        连接列表
    """
    conditions = [TestDataConnection.user_id == user_id]
    if is_active is not None:
        conditions.append(TestDataConnection.is_active == is_active)
    
    query = select(TestDataConnection).where(and_(*conditions))
    query = query.order_by(desc(TestDataConnection.is_default), TestDataConnection.name)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_connection_by_id(
    session: AsyncSession,
    connection_id: int,
    user_id: Optional[str] = None
) -> Optional[TestDataConnection]:
    """
    根据ID获取连接
    
    Args:
        session: 数据库会话
        connection_id: 连接ID
        user_id: 用户ID（用于验证所有权）
        
    Returns:
        连接对象，如果不存在则返回None
    """
    conditions = [TestDataConnection.id == connection_id]
    if user_id:
        conditions.append(TestDataConnection.user_id == user_id)
    
    query = select(TestDataConnection).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_connection(
    session: AsyncSession,
    user_id: str,
    data: Dict[str, Any]
) -> TestDataConnection:
    """
    创建数据库连接
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        data: 连接数据
        
    Returns:
        创建的连接对象
    """
    connection = TestDataConnection(
        user_id=user_id,
        **data
    )
    session.add(connection)
    await session.flush()
    await session.refresh(connection)
    return connection


async def update_connection(
    session: AsyncSession,
    connection_id: int,
    user_id: str,
    data: Dict[str, Any]
) -> Optional[TestDataConnection]:
    """
    更新数据库连接
    
    Args:
        session: 数据库会话
        connection_id: 连接ID
        user_id: 用户ID
        data: 更新数据
        
    Returns:
        更新后的连接对象，如果不存在则返回None
    """
    connection = await get_connection_by_id(session, connection_id, user_id)
    if not connection:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(connection, key, value)
    
    connection.updated_at = datetime.now()
    await session.flush()
    await session.refresh(connection)
    return connection


async def delete_connection(
    session: AsyncSession,
    connection_id: int,
    user_id: str
) -> bool:
    """
    删除数据库连接
    
    Args:
        session: 数据库会话
        connection_id: 连接ID
        user_id: 用户ID
        
    Returns:
        是否删除成功
    """
    stmt = delete(TestDataConnection).where(
        and_(
            TestDataConnection.id == connection_id,
            TestDataConnection.user_id == user_id
        )
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


async def set_default_connection(
    session: AsyncSession,
    connection_id: int,
    user_id: str
) -> bool:
    """
    设置默认连接
    
    Args:
        session: 数据库会话
        connection_id: 连接ID
        user_id: 用户ID
        
    Returns:
        是否设置成功
    """
    # 先清除其他默认连接
    await session.execute(
        update(TestDataConnection).where(
            and_(
                TestDataConnection.user_id == user_id,
                TestDataConnection.is_default == True
            )
        ).values(is_default=False)
    )
    
    # 设置新的默认连接
    connection = await get_connection_by_id(session, connection_id, user_id)
    if connection:
        connection.is_default = True
        await session.flush()
        return True
    return False


async def update_connection_status(
    session: AsyncSession,
    connection_id: int,
    status: ConnectionStatus,
    user_id: Optional[str] = None
) -> Optional[TestDataConnection]:
    """
    更新连接状态
    
    Args:
        session: 数据库会话
        connection_id: 连接ID
        status: 新状态
        user_id: 用户ID
        
    Returns:
        更新后的连接对象
    """
    connection = await get_connection_by_id(session, connection_id, user_id)
    if connection:
        connection.status = status
        if status == ConnectionStatus.CONNECTED:
            connection.last_connected_at = datetime.now()
        await session.flush()
        await session.refresh(connection)
    return connection


async def get_user_connection_count(
    session: AsyncSession,
    user_id: str
) -> int:
    """
    获取用户的连接数量
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        
    Returns:
        连接数量
    """
    from sqlalchemy import func
    query = select(func.count(TestDataConnection.id)).where(
        and_(
            TestDataConnection.user_id == user_id,
            TestDataConnection.is_active == True
        )
    )
    result = await session.execute(query)
    return result.scalar() or 0


# ============================================================================
# 操作日志 CRUD
# ============================================================================

async def get_operation_logs(
    session: AsyncSession,
    user_id: str,
    connection_id: Optional[int] = None,
    operation_type: Optional[OperationType] = None,
    limit: int = 100,
    offset: int = 0
) -> List[TestDataOperationLog]:
    """
    获取操作日志列表
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        connection_id: 连接ID（可选）
        operation_type: 操作类型（可选）
        limit: 返回数量限制
        offset: 偏移量
        
    Returns:
        日志列表
    """
    conditions = [TestDataOperationLog.user_id == user_id]
    if connection_id:
        conditions.append(TestDataOperationLog.connection_id == connection_id)
    if operation_type:
        conditions.append(TestDataOperationLog.operation_type == operation_type)
    
    query = select(TestDataOperationLog).where(and_(*conditions))
    query = query.order_by(desc(TestDataOperationLog.created_at))
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_operation_log_count(
    session: AsyncSession,
    user_id: str,
    connection_id: Optional[int] = None
) -> int:
    """
    获取操作日志数量
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        connection_id: 连接ID（可选）
        
    Returns:
        日志数量
    """
    from sqlalchemy import func
    conditions = [TestDataOperationLog.user_id == user_id]
    if connection_id:
        conditions.append(TestDataOperationLog.connection_id == connection_id)
    
    query = select(func.count(TestDataOperationLog.id)).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar() or 0


async def create_operation_log(
    session: AsyncSession,
    user_id: str,
    connection_id: int,
    operation_type: OperationType,
    status: OperationStatus,
    table_name: str,
    affected_rows: int = 0,
    sql_content: Optional[str] = None,
    error_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    execution_time_ms: Optional[int] = None
) -> TestDataOperationLog:
    """
    创建操作日志
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        connection_id: 连接ID
        operation_type: 操作类型
        status: 操作状态
        table_name: 表名
        affected_rows: 影响行数
        sql_content: SQL内容
        error_message: 错误信息
        details: 详细信息
        execution_time_ms: 执行时间
        
    Returns:
        创建的日志对象
    """
    log = TestDataOperationLog(
        user_id=user_id,
        connection_id=connection_id,
        operation_type=operation_type,
        status=status,
        table_name=table_name,
        affected_rows=affected_rows,
        sql_content=sql_content,
        error_message=error_message,
        details=details,
        execution_time_ms=execution_time_ms
    )
    session.add(log)
    await session.flush()
    await session.refresh(log)
    return log


async def delete_operation_logs(
    session: AsyncSession,
    user_id: str,
    connection_id: Optional[int] = None
) -> int:
    """
    删除操作日志
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        connection_id: 连接ID（可选，如果指定则只删除该连接的日志）
        
    Returns:
        删除的日志数量
    """
    conditions = [TestDataOperationLog.user_id == user_id]
    if connection_id:
        conditions.append(TestDataOperationLog.connection_id == connection_id)
    
    stmt = delete(TestDataOperationLog).where(and_(*conditions))
    result = await session.execute(stmt)
    return result.rowcount


# ============================================================================
# 历史输入 CRUD
# ============================================================================

async def get_input_history(
    session: AsyncSession,
    user_id: str,
    connection_id: Optional[int] = None,
    limit: int = 50
) -> List[TestDataInputHistory]:
    """
    获取历史输入记录
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        connection_id: 连接ID（可选）
        limit: 返回数量限制
        
    Returns:
        历史记录列表
    """
    conditions = [TestDataInputHistory.user_id == user_id]
    if connection_id:
        conditions.append(TestDataInputHistory.connection_id == connection_id)
    
    query = select(TestDataInputHistory).where(and_(*conditions))
    query = query.order_by(desc(TestDataInputHistory.created_at))
    query = query.limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_input_history(
    session: AsyncSession,
    user_id: str,
    input_content: str,
    connection_id: Optional[int] = None,
    model_id: Optional[str] = None,
    selected_tables: Optional[List[str]] = None
) -> TestDataInputHistory:
    """
    创建历史输入记录
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        input_content: 输入内容
        connection_id: 连接ID
        model_id: 模型ID
        selected_tables: 选择的表
        
    Returns:
        创建的历史记录
    """
    history = TestDataInputHistory(
        user_id=user_id,
        input_content=input_content,
        connection_id=connection_id,
        model_id=model_id,
        selected_tables=selected_tables
    )
    session.add(history)
    await session.flush()
    await session.refresh(history)
    
    # 保持历史记录不超过50条
    await _cleanup_old_history(session, user_id, limit=50)
    
    return history


async def delete_input_history(
    session: AsyncSession,
    history_id: int,
    user_id: str
) -> bool:
    """
    删除历史输入记录
    
    Args:
        session: 数据库会话
        history_id: 记录ID
        user_id: 用户ID
        
    Returns:
        是否删除成功
    """
    stmt = delete(TestDataInputHistory).where(
        and_(
            TestDataInputHistory.id == history_id,
            TestDataInputHistory.user_id == user_id
        )
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


async def _cleanup_old_history(
    session: AsyncSession,
    user_id: str,
    limit: int = 50
) -> None:
    """
    清理超出限制的旧历史记录
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        limit: 保留的最大记录数
    """
    from sqlalchemy import func
    
    # 获取总数
    count_query = select(func.count(TestDataInputHistory.id)).where(
        TestDataInputHistory.user_id == user_id
    )
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    
    if total > limit:
        # 找到需要删除的记录ID
        subquery = select(TestDataInputHistory.id).where(
            TestDataInputHistory.user_id == user_id
        ).order_by(desc(TestDataInputHistory.created_at)).limit(limit)
        
        # 删除不在最新limit条中的记录
        delete_stmt = delete(TestDataInputHistory).where(
            and_(
                TestDataInputHistory.user_id == user_id,
                TestDataInputHistory.id.notin_(subquery)
            )
        )
        await session.execute(delete_stmt)
