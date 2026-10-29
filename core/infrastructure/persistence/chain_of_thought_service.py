#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
思维链数据库服务
负责将思维链数据保存到数据库
"""
from typing import Optional
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.inner_models.chain_of_thought_model import (
    ChainOfThoughtModel,
    ThoughtStepModel,
    ThoughtLogModel
)
from core.models.chain_of_thought import ChainOfThought, ThoughtStep


class ChainOfThoughtService:
    """思维链数据库服务"""

    def __init__(self, db_session: Optional[AsyncSession] = None):
        """
        初始化服务
        
        Args:
            db_session: 数据库会话（可选，如果不提供则只记录日志不保存到数据库）
        """
        self.db_session = db_session
        self.enabled = db_session is not None

    async def save_chain(self, chain: ChainOfThought) -> Optional[str]:
        """
        保存思维链到数据库
        
        Args:
            chain: 思维链对象
            
        Returns:
            保存的思维链ID，如果保存失败则返回None
        """
        if not self.enabled:
            logger.debug("数据库会话未提供，跳过保存思维链")
            return None

        try:
            # 检查是否已存在
            stmt = select(ChainOfThoughtModel).where(
                ChainOfThoughtModel.thought_id == chain.thought_id
            )
            result = await self.db_session.execute(stmt)
            existing_chain = result.scalar_one_or_none()

            if existing_chain:
                # 更新现有记录
                await self._update_chain_model(existing_chain, chain)
            else:
                # 创建新记录
                chain_model = await self._create_chain_model(chain)
                self.db_session.add(chain_model)

            # 保存步骤
            await self._save_steps(chain)

            # 提交事务
            await self.db_session.commit()
            logger.info(f"思维链已保存到数据库: {chain.thought_id}")
            return chain.thought_id

        except Exception as e:
            logger.error(f"保存思维链失败: {e}", exc_info=True)
            await self.db_session.rollback()
            return None

    async def _create_chain_model(self, chain: ChainOfThought) -> ChainOfThoughtModel:
        """创建思维链模型"""
        import json
        
        return ChainOfThoughtModel(
            thought_id=chain.thought_id,
            task_id=chain.task_id,
            session_id=chain.session_id,
            original_task=chain.original_task,
            goal=chain.goal,
            status=chain.status,
            current_step=chain.current_step,
            progress=chain.get_progress(),
            context=chain.context,
            intermediate_results=chain.intermediate_results,
            final_result=json.dumps(chain.final_result, ensure_ascii=False) if chain.final_result else None,
            error=chain.error,
            created_at=chain.created_at,
            updated_at=chain.updated_at,
            completed_at=chain.completed_at
        )

    async def _update_chain_model(self, chain_model: ChainOfThoughtModel, chain: ChainOfThought):
        """更新思维链模型"""
        import json
        
        chain_model.status = chain.status
        chain_model.current_step = chain.current_step
        chain_model.progress = chain.get_progress()
        chain_model.context = chain.context
        chain_model.intermediate_results = chain.intermediate_results
        chain_model.final_result = json.dumps(chain.final_result, ensure_ascii=False) if chain.final_result else None
        chain_model.error = chain.error
        chain_model.updated_at = chain.updated_at
        chain_model.completed_at = chain.completed_at

    async def _save_steps(self, chain: ChainOfThought):
        """保存思维步骤"""
        for step in chain.steps:
            # 检查步骤是否已存在
            stmt = select(ThoughtStepModel).where(
                ThoughtStepModel.step_id == step.step_id
            )
            result = await self.db_session.execute(stmt)
            existing_step = result.scalar_one_or_none()

            if existing_step:
                # 更新现有步骤
                await self._update_step_model(existing_step, step)
            else:
                # 创建新步骤
                step_model = await self._create_step_model(chain.thought_id, step)
                self.db_session.add(step_model)

    async def _create_step_model(self, thought_id: str, step: ThoughtStep) -> ThoughtStepModel:
        """创建思维步骤模型"""

        return ThoughtStepModel(
            step_id=step.step_id,
            thought_id=thought_id,
            step_number=step.step_number,
            thought_type=step.thought_type.value,
            description=step.description,
            reasoning=step.reasoning,
            status=step.status.value,
            tool_name=step.tool_name,
            tool_parameters=step.tool_parameters,
            result=step.result if isinstance(step.result, (dict, list)) else {"value": step.result} if step.result else None,
            error=step.error,
            dependencies=step.dependencies,
            meta_data=step.meta_data,
            created_at=step.created_at,
            started_at=step.started_at,
            completed_at=step.completed_at
        )

    async def _update_step_model(self, step_model: ThoughtStepModel, step: ThoughtStep):
        """更新思维步骤模型"""

        step_model.thought_type = step.thought_type.value
        step_model.description = step.description
        step_model.reasoning = step.reasoning
        step_model.status = step.status.value
        step_model.tool_name = step.tool_name
        step_model.tool_parameters = step.tool_parameters
        step_model.result = step.result if isinstance(step.result, (dict, list)) else {"value": step.result} if step.result else None
        step_model.error = step.error
        step_model.dependencies = step.dependencies
        step_model.meta_data = step.meta_data
        step_model.started_at = step.started_at
        step_model.completed_at = step.completed_at

    async def log_event(
        self,
        thought_id: str,
        log_type: str,
        message: str,
        log_level: str = "info",
        step_id: Optional[str] = None,
        details: Optional[dict] = None
    ):
        """
        记录思维链事件日志
        
        Args:
            thought_id: 思维链ID
            log_type: 日志类型
            message: 日志消息
            log_level: 日志级别（debug/info/warning/error）
            step_id: 关联的步骤ID（可选）
            details: 详细信息（可选）
        """
        if not self.enabled:
            logger.debug(f"[思维链日志] {log_type}: {message}")
            return

        try:
            log_model = ThoughtLogModel(
                thought_id=thought_id,
                step_id=step_id,
                log_level=log_level,
                log_type=log_type,
                message=message,
                details=details or {},
                created_at=datetime.now()
            )
            self.db_session.add(log_model)
            await self.db_session.commit()
            logger.info(f"思维链日志已保存: {thought_id} - {log_type}")
        except Exception as e:
            logger.error(f"保存思维链日志失败: {e}", exc_info=True)
            await self.db_session.rollback()

    async def get_chain(self, thought_id: str) -> Optional[ChainOfThoughtModel]:
        """
        从数据库获取思维链
        
        Args:
            thought_id: 思维链ID
            
        Returns:
            思维链模型，如果不存在则返回None
        """
        if not self.enabled:
            return None

        try:
            stmt = select(ChainOfThoughtModel).where(
                ChainOfThoughtModel.thought_id == thought_id
            )
            result = await self.db_session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取思维链失败: {e}", exc_info=True)
            return None

    async def get_chain_logs(
        self,
        thought_id: str,
        limit: int = 100
    ) -> list:
        """
        获取思维链的日志
        
        Args:
            thought_id: 思维链ID
            limit: 返回数量限制
            
        Returns:
            日志列表
        """
        if not self.enabled:
            return []

        try:
            stmt = select(ThoughtLogModel).where(
                ThoughtLogModel.thought_id == thought_id
            ).order_by(ThoughtLogModel.created_at.desc()).limit(limit)
            result = await self.db_session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"获取思维链日志失败: {e}", exc_info=True)
            return []

