#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/27
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
测试数据生成器数据库模型
包含：数据库连接配置、操作日志、历史输入记录
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, Enum as SQLEnum
from enum import Enum as PyEnum

from models.inner_models.base import Base


class DatabaseType(str, PyEnum):
    """数据库类型枚举"""
    MYSQL = "mysql"


class ConnectionStatus(str, PyEnum):
    """连接状态枚举"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class OperationType(str, PyEnum):
    """操作类型枚举"""
    INSERT = "insert"
    UPDATE = "update"
    QUERY = "query"


class OperationStatus(str, PyEnum):
    """操作状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    PROCESSING = "processing"


class TestDataConnection(Base):
    """数据库连接配置表"""
    __tablename__ = "test_data_connections"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="连接ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户ID")
    name = Column(String(100), nullable=False, comment="连接名称")
    db_type = Column(SQLEnum(DatabaseType, values_callable=lambda x: [e.value for e in x]), default=DatabaseType.MYSQL, nullable=False, comment="数据库类型")
    host = Column(String(255), nullable=False, default="localhost", comment="主机地址")
    port = Column(Integer, nullable=False, default=3306, comment="端口")
    database = Column(String(100), nullable=False, comment="数据库名称")
    username = Column(String(100), nullable=False, comment="用户名")
    password = Column(String(255), nullable=True, comment="密码（加密存储）")
    status = Column(SQLEnum(ConnectionStatus, values_callable=lambda x: [e.value for e in x]), default=ConnectionStatus.DISCONNECTED, comment="连接状态")
    is_default = Column(Boolean, default=False, nullable=False, comment="是否为默认连接")
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment="是否启用")
    last_connected_at = Column(DateTime, nullable=True, comment="最后连接时间")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<TestDataConnection(id={self.id}, name={self.name}, host={self.host}, database={self.database})>"


class TestDataOperationLog(Base):
    """操作日志表"""
    __tablename__ = "test_data_operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="日志ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户ID")
    connection_id = Column(Integer, nullable=False, index=True, comment="连接ID")
    operation_type = Column(SQLEnum(OperationType, values_callable=lambda x: [e.value for e in x]), nullable=False, comment="操作类型")
    status = Column(SQLEnum(OperationStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, comment="操作状态")
    table_name = Column(String(100), nullable=False, comment="表名")
    affected_rows = Column(Integer, default=0, comment="影响行数")
    sql_content = Column(Text, nullable=True, comment="执行的SQL语句")
    error_message = Column(Text, nullable=True, comment="错误信息")
    details = Column(JSON, nullable=True, comment="详细信息（JSON格式）")
    execution_time_ms = Column(Integer, nullable=True, comment="执行时间（毫秒）")
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True, comment="创建时间")

    def __repr__(self):
        return f"<TestDataOperationLog(id={self.id}, table={self.table_name}, type={self.operation_type}, status={self.status})>"


class TestDataInputHistory(Base):
    """历史输入记录表"""
    __tablename__ = "test_data_input_history"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户ID")
    connection_id = Column(Integer, nullable=True, index=True, comment="连接ID")
    input_content = Column(Text, nullable=False, comment="输入内容")
    model_id = Column(String(100), nullable=True, comment="使用的模型ID")
    selected_tables = Column(JSON, nullable=True, comment="选择的表（JSON数组）")
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True, comment="创建时间")

    def __repr__(self):
        return f"<TestDataInputHistory(id={self.id}, user_id={self.user_id})>"
