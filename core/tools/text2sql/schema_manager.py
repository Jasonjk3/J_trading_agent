#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/26
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Schema 管理器
用于获取和缓存数据库表结构信息
"""
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class SchemaManager:
    """数据库 Schema 管理器，用于获取和缓存表结构信息"""
    
    def __init__(
        self,
        cache_ttl: int = 3600,  # 缓存过期时间（秒）
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
        excluded_tables: Optional[List[str]] = None
    ):
        """
        初始化 Schema 管理器
        
        Args:
            cache_ttl: 缓存过期时间（秒），默认 1 小时
            allowed_schemas: 允许查询的 schema 列表，None 表示允许所有
            allowed_tables: 允许查询的表列表，None 表示允许所有
            excluded_tables: 排除的表列表
        """
        self.cache_ttl = cache_ttl
        self.allowed_schemas = set(allowed_schemas) if allowed_schemas else None
        self.allowed_tables = set(allowed_tables) if allowed_tables else None
        self.excluded_tables = set(excluded_tables) if excluded_tables else set()
        
        # 缓存结构：{schema.table_name: {"info": ..., "cached_at": ...}}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._full_schema_cache: Optional[Dict[str, Any]] = None
        self._full_schema_cached_at: Optional[datetime] = None
    
    def _is_cache_valid(self, cached_at: Optional[datetime]) -> bool:
        """检查缓存是否有效"""
        if cached_at is None:
            return False
        return datetime.now() - cached_at < timedelta(seconds=self.cache_ttl)
    
    def _is_table_allowed(self, schema: str, table_name: str) -> bool:
        """检查表是否允许访问"""
        full_name = f"{schema}.{table_name}"
        
        # 检查是否在排除列表中
        if table_name in self.excluded_tables or full_name in self.excluded_tables:
            return False
        
        # 检查 schema 是否允许
        if self.allowed_schemas and schema not in self.allowed_schemas:
            return False
        
        # 检查表是否允许
        if self.allowed_tables:
            return table_name in self.allowed_tables or full_name in self.allowed_tables
        
        return True
    
    async def get_schema_info(
        self,
        session: AsyncSession,
        tables: Optional[List[str]] = None,
        schemas: Optional[List[str]] = None,
        include_sample_data: bool = False,
        sample_rows: int = 3
    ) -> str:
        """
        获取数据库表结构信息（用于提供给 LLM）
        
        Args:
            session: 数据库会话
            tables: 指定的表名列表，None 表示获取所有允许的表
            schemas: 指定的 schema 列表，None 表示使用默认配置
            include_sample_data: 是否包含样本数据
            sample_rows: 样本数据行数
            
        Returns:
            格式化的表结构信息字符串
        """
        try:
            # 获取当前数据库名
            result = await session.execute(text("SELECT DATABASE()"))
            current_db = result.scalar()
            
            # 确定要查询的 schema
            target_schemas = schemas or (list(self.allowed_schemas) if self.allowed_schemas else [current_db])
            
            schema_info_parts = []
            
            for schema in target_schemas:
                # 获取该 schema 下的所有表
                tables_query = text("""
                    SELECT TABLE_NAME, TABLE_COMMENT 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = :schema
                    ORDER BY TABLE_NAME
                """)
                result = await session.execute(tables_query, {"schema": schema})
                all_tables = result.fetchall()
                
                for row in all_tables:
                    # 使用索引访问，更安全
                    table_name = row[0]
                    table_comment = row[1] if len(row) > 1 else ""
                    
                    # 如果指定了表，只处理指定的表
                    if tables and table_name not in tables:
                        continue
                    
                    # 检查表是否允许
                    if not self._is_table_allowed(schema, table_name):
                        continue
                    
                    # 获取表结构信息
                    table_info = await self._get_table_info(session, schema, table_name, table_comment)
                    
                    if include_sample_data:
                        sample_data = await self._get_sample_data(session, schema, table_name, sample_rows)
                        table_info += f"\n  示例数据:\n{sample_data}"
                    
                    schema_info_parts.append(table_info)
            
            if not schema_info_parts:
                return "未找到可用的表结构信息"
            
            return "\n\n".join(schema_info_parts)
            
        except Exception as e:
            logger.error(f"获取 Schema 信息失败: {e}", exc_info=True)
            return f"获取表结构信息失败: {str(e)}"
    
    async def _get_table_info(
        self,
        session: AsyncSession,
        schema: str,
        table_name: str,
        table_comment: str
    ) -> str:
        """获取单个表的结构信息"""
        cache_key = f"{schema}.{table_name}"
        
        # 检查缓存
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_cache_valid(cached.get("cached_at")):
                return cached["info"]
        
        try:
            # 获取列信息
            columns_query = text("""
                SELECT 
                    COLUMN_NAME,
                    COLUMN_TYPE,
                    IS_NULLABLE,
                    COLUMN_KEY,
                    COLUMN_DEFAULT,
                    COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
            """)
            result = await session.execute(columns_query, {"schema": schema, "table_name": table_name})
            columns = result.fetchall()
            
            # 构建表信息字符串
            info_lines = [f"表名: {schema}.{table_name}"]
            if table_comment:
                info_lines.append(f"描述: {table_comment}")
            info_lines.append("字段:")
            
            for col in columns:
                # 使用索引访问，更安全
                col_name = col[0]
                col_type = col[1] if len(col) > 1 else "unknown"
                nullable = col[2] if len(col) > 2 else "YES"
                key = col[3] if len(col) > 3 else ""
                default = col[4] if len(col) > 4 else None
                comment = col[5] if len(col) > 5 else ""
                col_info = f"  - {col_name} ({col_type})"
                
                markers = []
                if key == "PRI":
                    markers.append("主键")
                elif key == "UNI":
                    markers.append("唯一")
                elif key == "MUL":
                    markers.append("索引")
                
                if nullable == "NO":
                    markers.append("非空")
                
                if markers:
                    col_info += f" [{', '.join(markers)}]"
                
                if comment:
                    col_info += f" -- {comment}"
                
                info_lines.append(col_info)
            
            info = "\n".join(info_lines)
            
            # 更新缓存
            self._cache[cache_key] = {
                "info": info,
                "cached_at": datetime.now()
            }
            
            return info
            
        except Exception as e:
            logger.error(f"获取表 {cache_key} 信息失败: {e}")
            return f"表 {cache_key}: 获取结构失败"
    
    async def _get_sample_data(
        self,
        session: AsyncSession,
        schema: str,
        table_name: str,
        limit: int = 3
    ) -> str:
        """获取表的样本数据"""
        try:
            query = text(f"SELECT * FROM `{schema}`.`{table_name}` LIMIT :limit")
            result = await session.execute(query, {"limit": limit})
            rows = result.fetchall()
            columns = result.keys()
            
            if not rows:
                return "    (无数据)"
            
            # 格式化样本数据
            sample_lines = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                # 只显示前几个字段，避免太长
                display_items = list(row_dict.items())[:6]
                row_str = ", ".join([f"{k}={v}" for k, v in display_items])
                if len(row_dict) > 6:
                    row_str += ", ..."
                sample_lines.append(f"    {{{row_str}}}")
            
            return "\n".join(sample_lines)
            
        except Exception as e:
            logger.warning(f"获取样本数据失败: {e}")
            return "    (获取样本数据失败)"
    
    async def get_table_list(
        self,
        session: AsyncSession,
        schema: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        获取表列表
        
        Args:
            session: 数据库会话
            schema: 指定的 schema，None 表示当前数据库
            
        Returns:
            表信息列表 [{"schema": ..., "table_name": ..., "comment": ...}, ...]
        """
        try:
            if schema is None:
                result = await session.execute(text("SELECT DATABASE()"))
                schema = result.scalar()
            
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_COMMENT 
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = :schema
                ORDER BY TABLE_NAME
            """)
            result = await session.execute(query, {"schema": schema})
            rows = result.fetchall()
            
            tables = []
            for row in rows:
                # 使用索引访问，更安全
                table_schema = row[0]
                table_name = row[1] if len(row) > 1 else ""
                comment = row[2] if len(row) > 2 else ""
                if self._is_table_allowed(table_schema, table_name):
                    tables.append({
                        "schema": table_schema,
                        "table_name": table_name,
                        "comment": comment or ""
                    })
            
            return tables
            
        except Exception as e:
            logger.error(f"获取表列表失败: {e}")
            return []
    
    def clear_cache(self, table_name: Optional[str] = None):
        """
        清除缓存
        
        Args:
            table_name: 指定要清除的表名，None 表示清除所有缓存
        """
        if table_name:
            if table_name in self._cache:
                del self._cache[table_name]
        else:
            self._cache.clear()
            self._full_schema_cache = None
            self._full_schema_cached_at = None
        
        logger.info(f"Schema 缓存已清除: {table_name or '全部'}")

