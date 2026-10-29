#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/26
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
SQL 执行器
安全地执行 SQL 查询并返回结果
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SQLExecutor:
    """SQL 执行器，用于安全执行 SQL 查询"""
    
    # 危险操作关键字（不允许执行）
    DANGEROUS_KEYWORDS = [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", 
        "INSERT", "UPDATE", "REPLACE", "GRANT", "REVOKE",
        "RENAME", "EXECUTE", "CALL"
    ]
    
    # 允许的只读操作
    ALLOWED_KEYWORDS = ["SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"]
    
    def __init__(
        self,
        max_results: int = 100,
        timeout: int = 30,
        allow_write: bool = False,
        allowed_schemas: Optional[List[str]] = None
    ):
        """
        初始化 SQL 执行器
        
        Args:
            max_results: 最大返回结果数
            timeout: 查询超时时间（秒）
            allow_write: 是否允许写操作（默认不允许，只读）
            allowed_schemas: 允许访问的 schema 列表
        """
        self.max_results = max_results
        self.timeout = timeout
        self.allow_write = allow_write
        self.allowed_schemas = set(allowed_schemas) if allowed_schemas else None
    
    def validate_sql(self, sql: str) -> Tuple[bool, str]:
        """
        验证 SQL 语句是否安全
        
        Args:
            sql: SQL 语句
            
        Returns:
            (是否安全, 错误信息)
        """
        if not sql or not sql.strip():
            return False, "SQL 语句不能为空"
        
        # 清理 SQL（移除注释和多余空格）
        cleaned_sql = self._clean_sql(sql)
        sql_upper = cleaned_sql.upper()
        
        # 检查是否以允许的关键字开头
        first_word = sql_upper.split()[0] if sql_upper.split() else ""
        
        if not self.allow_write:
            # 只读模式：只允许 SELECT 等查询操作
            if first_word not in self.ALLOWED_KEYWORDS:
                return False, f"只允许执行查询操作，不支持 {first_word}"
            
            # 检查是否包含危险关键字
            for keyword in self.DANGEROUS_KEYWORDS:
                # 使用正则确保是完整单词匹配
                pattern = r'\b' + keyword + r'\b'
                if re.search(pattern, sql_upper):
                    return False, f"SQL 包含不允许的操作: {keyword}"
        
        # 检查是否有 SQL 注入风险
        injection_patterns = [
            r';\s*--',  # 注释注入
            r';\s*DROP',
            r';\s*DELETE',
            r'UNION\s+SELECT',  # UNION 注入（可选，有时是合法的）
            r"'\s*OR\s+'1'\s*=\s*'1",  # 经典注入
            r'"\s*OR\s+"1"\s*=\s*"1',
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, sql_upper):
                return False, f"检测到潜在的 SQL 注入风险"
        
        # 检查 schema 访问限制
        if self.allowed_schemas:
            # 提取 SQL 中的表名（简单实现，可能需要更复杂的解析）
            table_refs = self._extract_table_references(cleaned_sql)
            for schema, table in table_refs:
                if schema and schema not in self.allowed_schemas:
                    return False, f"不允许访问 schema: {schema}"
        
        return True, ""
    
    def _clean_sql(self, sql: str) -> str:
        """清理 SQL 语句"""
        # 移除 markdown 代码块标记
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*', '', sql)
        
        # 移除单行注释
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        
        # 移除多行注释
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        # 移除多余空格
        sql = ' '.join(sql.split())
        
        return sql.strip()
    
    def _extract_table_references(self, sql: str) -> List[Tuple[Optional[str], str]]:
        """
        提取 SQL 中的表引用
        
        Returns:
            [(schema, table_name), ...]
        """
        tables = []
        
        # 匹配 FROM 和 JOIN 后的表名
        # 支持格式: table_name, schema.table_name, `schema`.`table_name`
        patterns = [
            r'FROM\s+`?(\w+)`?\.`?(\w+)`?',  # schema.table
            r'FROM\s+`?(\w+)`?(?:\s|$|,)',  # table only
            r'JOIN\s+`?(\w+)`?\.`?(\w+)`?',  # schema.table in JOIN
            r'JOIN\s+`?(\w+)`?(?:\s|$)',  # table only in JOIN
        ]
        
        # 模式0和2是 schema.table 格式（2个捕获组）
        for pattern in [patterns[0], patterns[2]]:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    tables.append((match[0], match[1]))
        
        # 模式1和3是 table only 格式（1个捕获组）
        for pattern in [patterns[1], patterns[3]]:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str):
                    tables.append((None, match))
                elif isinstance(match, tuple) and len(match) >= 1:
                    tables.append((None, match[0]))
        
        return tables
    
    async def execute(
        self,
        session: AsyncSession,
        sql: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行 SQL 查询
        
        Args:
            session: 数据库会话
            sql: SQL 语句
            params: 参数字典（用于参数化查询）
            
        Returns:
            {
                "success": True/False,
                "data": [...],  # 查询结果
                "columns": [...],  # 列名
                "row_count": int,  # 行数
                "error": str  # 错误信息（如果失败）
            }
        """
        try:
            # 验证 SQL
            is_valid, error_msg = self.validate_sql(sql)
            if not is_valid:
                return {
                    "success": False,
                    "error": error_msg,
                    "sql": sql
                }
            
            # 清理 SQL
            cleaned_sql = self._clean_sql(sql)
            
            # 自动添加 LIMIT（如果没有的话）
            cleaned_sql = self._ensure_limit(cleaned_sql)
            
            logger.info(f"执行 SQL: {cleaned_sql[:200]}...")
            
            # 执行查询
            if params:
                result = await session.execute(text(cleaned_sql), params)
            else:
                result = await session.execute(text(cleaned_sql))
            
            # 获取结果
            rows = result.fetchall()
            columns = list(result.keys())
            
            # 转换结果为可序列化格式
            data = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    row_dict[col] = self._serialize_value(value)
                data.append(row_dict)
            
            return {
                "success": True,
                "data": data,
                "columns": columns,
                "row_count": len(data),
                "sql": cleaned_sql
            }
            
        except Exception as e:
            logger.error(f"SQL 执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "sql": sql
            }
    
    def _ensure_limit(self, sql: str) -> str:
        """确保 SQL 有 LIMIT 限制"""
        sql_upper = sql.upper()
        
        # 如果已经有 LIMIT，不做修改
        if "LIMIT" in sql_upper:
            return sql
        
        # 只对 SELECT 语句添加 LIMIT
        if not sql_upper.strip().startswith("SELECT"):
            return sql
        
        # 在 SQL 末尾添加 LIMIT
        # 注意处理可能存在的分号
        sql = sql.rstrip().rstrip(';')
        sql = f"{sql} LIMIT {self.max_results}"
        
        return sql
    
    def _serialize_value(self, value: Any) -> Any:
        """将值转换为可序列化格式"""
        if value is None:
            return None
        elif isinstance(value, (datetime,)):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, (date,)):
            return value.strftime("%Y-%m-%d")
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, bytes):
            try:
                return value.decode('utf-8')
            except UnicodeDecodeError:
                return str(value)
        elif isinstance(value, (int, float, str, bool)):
            return value
        else:
            return str(value)
    
    async def explain(
        self,
        session: AsyncSession,
        sql: str
    ) -> Dict[str, Any]:
        """
        获取 SQL 执行计划
        
        Args:
            session: 数据库会话
            sql: SQL 语句
            
        Returns:
            执行计划信息
        """
        try:
            # 验证 SQL
            is_valid, error_msg = self.validate_sql(sql)
            if not is_valid:
                return {
                    "success": False,
                    "error": error_msg
                }
            
            cleaned_sql = self._clean_sql(sql)
            explain_sql = f"EXPLAIN {cleaned_sql}"
            
            result = await session.execute(text(explain_sql))
            rows = result.fetchall()
            columns = list(result.keys())
            
            explain_data = []
            for row in rows:
                row_dict = dict(zip(columns, [self._serialize_value(v) for v in row]))
                explain_data.append(row_dict)
            
            return {
                "success": True,
                "explain": explain_data,
                "sql": cleaned_sql
            }
            
        except Exception as e:
            logger.error(f"获取执行计划失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

