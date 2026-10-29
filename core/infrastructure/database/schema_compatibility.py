#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动期关键数据库兼容性检查。"""

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine


_BACKTEST_STATUS_COLUMN_SQL = text(
    """
    SELECT COLUMN_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'backtest_tasks'
      AND COLUMN_NAME = 'status'
    """
)
_SHORT_METADATA_LOCK_WAIT_SQL = text("SET SESSION lock_wait_timeout = 2")
_ADD_CANCELLED_STATUS_SQL = text(
    """
    ALTER TABLE `backtest_tasks`
    MODIFY COLUMN `status`
    ENUM('pending', 'running', 'completed', 'failed', 'cancelled')
    NOT NULL DEFAULT 'pending' COMMENT '任务状态'
    """
)

_CREATE_MESSAGE_PUSH_TABLE_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS `message_push_configs` (
      `id` VARCHAR(36) NOT NULL,
      `user_id` VARCHAR(36) NOT NULL,
      `bot_type` ENUM('webhook','app') NOT NULL,
      `name` VARCHAR(100) NOT NULL,
      `description` VARCHAR(500) NULL,
      `webhook` TEXT NULL,
      `secret` TEXT NULL,
      `app_id` TEXT NULL,
      `app_secret` TEXT NULL,
      `receive_type` ENUM('chat_id','open_id','user_id','email') NULL,
      `receive_id` TEXT NULL,
      `enabled` TINYINT(1) NOT NULL DEFAULT 1,
      `last_test_status` ENUM('never','success','failed') NOT NULL DEFAULT 'never',
      `last_test_at` DATETIME NULL,
      `last_error` VARCHAR(500) NULL,
      `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`),
      KEY `idx_message_push_user` (`user_id`),
      KEY `idx_message_push_user_type` (`user_id`,`bot_type`),
      KEY `idx_message_push_user_enabled` (`user_id`,`enabled`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
)


def enum_column_contains(column_type: str | None, value: str) -> bool:
    if not column_type:
        return False
    return f"'{value.lower()}'" in column_type.lower()


async def ensure_runtime_schema_compatibility(engine: AsyncEngine) -> bool:
    """幂等补齐旧库 ENUM；锁繁忙时快速放弃，绝不阻塞业务请求。"""
    async with engine.begin() as connection:
        result = await connection.execute(_BACKTEST_STATUS_COLUMN_SQL)
        column_type = result.scalar_one_or_none()
        if column_type is None:
            logger.warning("未找到 backtest_tasks.status，跳过回测状态兼容迁移")
            return False
        if enum_column_contains(column_type, "cancelled"):
            return False

        await connection.execute(_SHORT_METADATA_LOCK_WAIT_SQL)
        try:
            await connection.execute(_ADD_CANCELLED_STATUS_SQL)
        except DBAPIError as exc:
            logger.error(
                "backtest_tasks.status 兼容迁移未执行（2 秒内未取得锁或无 DDL 权限）；"
                "请在无回测运行时执行 migrations/011_add_backtest_cancelled_status.sql: {}",
                exc,
            )
            return False

        logger.info("backtest_tasks.status 已增加 cancelled 状态")
        return True


async def ensure_message_push_schema(engine: AsyncEngine) -> bool:
    """幂等创建消息推送配置表，正式环境亦可执行对应 migration。"""
    try:
        async with engine.begin() as connection:
            await connection.execute(_CREATE_MESSAGE_PUSH_TABLE_SQL)
        return True
    except DBAPIError as exc:
        logger.error(
            "message_push_configs 初始化失败；请执行 migrations/018_create_message_push_configs.sql: {}",
            exc,
        )
        return False


async def ensure_data_monitor_schema(engine: AsyncEngine) -> bool:
    """Create monitoring tables for existing installations."""
    from models.inner_models.base import Base
    from models.inner_models.data_monitor_model import (
        MonitorEventModel, MonitorRuleModel, MonitorSampleModel, MonitorTaskModel, MonitorTemplateModel,
    )

    tables = [model.__table__ for model in (MonitorRuleModel, MonitorTemplateModel, MonitorTaskModel, MonitorEventModel, MonitorSampleModel)]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
            for table in ("data_monitor_rules", "data_monitor_tasks"):
                columns = (await connection.execute(text(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
                ), {"table_name": table})).scalars().all()
                additions = {
                    "rule_type": "VARCHAR(20) NOT NULL DEFAULT 'threshold'",
                    "window_minutes": "INT NULL",
                    "movement_unit": "VARCHAR(10) NULL",
                    "movement_direction": "VARCHAR(10) NULL",
                    "start_time": "VARCHAR(5) NULL",
                    "end_time": "VARCHAR(5) NULL",
                    "report_interval_minutes": "INT NULL",
                }
                for column, definition in additions.items():
                    if column not in columns:
                        await connection.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}"))
        return True
    except DBAPIError as exc:
        logger.error("数据监控表初始化失败；请执行 migrations/020_create_data_monitor.sql: {}", exc)
        return False
