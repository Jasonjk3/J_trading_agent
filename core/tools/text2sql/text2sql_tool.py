#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/26
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Text2SQL 工具
将自然语言转换为 SQL 查询并执行
"""
import json
import re
from typing import Any, Dict, List, Optional
from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.tools.base.base_tool import BaseTool
from core.tools.text2sql.schema_manager import SchemaManager
from core.tools.text2sql.sql_executor import SQLExecutor
from core.llm.base.base_llm import BaseLLM


class Text2SQLTool(BaseTool):
    """Text2SQL 工具，将自然语言转换为 SQL 查询并执行，支持多数据源"""
    
    def __init__(
        self,
        llm: BaseLLM,
        db_url: Optional[str] = None,
        db_sources: Optional[Dict[str, Dict[str, Any]]] = None,
        default_source: Optional[str] = None,
        max_results: int = 100,
        cache_schema: bool = True,
        schema_cache_ttl: int = 3600,
        allowed_schemas: Optional[List[str]] = None,
        allowed_tables: Optional[List[str]] = None,
        excluded_tables: Optional[List[str]] = None,
        include_sample_data: bool = False
    ):
        """
        初始化 Text2SQL 工具
        
        Args:
            llm: LLM 实例（用于生成 SQL）
            db_url: 单数据库连接 URL（简单模式，与 db_sources 二选一）
            db_sources: 多数据源配置，格式：
                {
                    "erp": {
                        "url": "mysql+aiomysql://user:pass@host/erp_db",
                        "description": "ERP 业务数据库，包含订单、产品、客户等数据",
                        "allowed_schemas": ["xt_business_data"],
                    },
                    "finance": {
                        "url": "mysql+aiomysql://user:pass@host/finance_db",
                        "description": "财务数据库，包含账户、交易、报表等数据",
                        "allowed_schemas": ["finance_data"],
                    }
                }
            default_source: 默认数据源名称（不指定时使用第一个）
            max_results: 最大返回结果数
            cache_schema: 是否缓存表结构
            schema_cache_ttl: Schema 缓存过期时间（秒）
            allowed_schemas: 允许访问的 schema 列表（单数据源模式使用）
            allowed_tables: 允许访问的表列表
            excluded_tables: 排除的表列表
            include_sample_data: 是否在 Schema 信息中包含样本数据
        """
        # 构建工具描述（明确只读模式）
        if db_sources and len(db_sources) > 1:
            sources_desc = "、".join(db_sources.keys())
            description = f"【只读】将自然语言问题转换为 SQL 查询并执行。仅支持 SELECT 查询，不支持 INSERT/UPDATE/DELETE 等数据修改。支持多个数据源（{sources_desc}），可通过 source 参数指定"
        else:
            description = "【只读】将自然语言问题转换为 SQL 查询并执行，返回查询结果。仅支持 SELECT 等只读操作，不支持 INSERT/UPDATE/DELETE 等数据修改"
        
        super().__init__(
            tool_name="text2sql",
            tool_description=description,
            tool_type="data_query"
        )
        
        self.llm = llm
        self.max_results = max_results
        self.include_sample_data = include_sample_data
        self.cache_schema = cache_schema
        self.schema_cache_ttl = schema_cache_ttl
        self.global_allowed_schemas = allowed_schemas
        self.global_allowed_tables = allowed_tables
        self.global_excluded_tables = excluded_tables
        
        # 初始化数据源配置
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._engines: Dict[str, Any] = {}
        self._session_factories: Dict[str, Any] = {}
        self._schema_managers: Dict[str, SchemaManager] = {}
        self._sql_executors: Dict[str, SQLExecutor] = {}
        
        # 处理数据源配置
        if db_sources:
            # 多数据源模式
            for name, config in db_sources.items():
                self._add_source(name, config)
            self.default_source = default_source or list(db_sources.keys())[0]
        elif db_url:
            # 单数据源模式（兼容旧配置）
            self._add_source("default", {
                "url": db_url,
                "description": "默认数据库",
                "allowed_schemas": allowed_schemas,
                "allowed_tables": allowed_tables,
                "excluded_tables": excluded_tables,
            })
            self.default_source = "default"
        else:
            raise ValueError("必须提供 db_url 或 db_sources 参数")
    
    def _add_source(self, name: str, config: Dict[str, Any]) -> None:
        """添加数据源"""
        url = config.get("url")
        if not url:
            raise ValueError(f"数据源 {name} 缺少 url 配置")
        
        self._sources[name] = {
            "url": url,
            "description": config.get("description", f"数据源 {name}"),
            "allowed_schemas": config.get("allowed_schemas") or self.global_allowed_schemas,
            "allowed_tables": config.get("allowed_tables") or self.global_allowed_tables,
            "excluded_tables": config.get("excluded_tables") or self.global_excluded_tables,
        }
        
        # 为每个数据源创建独立的 SchemaManager 和 SQLExecutor
        source_config = self._sources[name]
        self._schema_managers[name] = SchemaManager(
            cache_ttl=self.schema_cache_ttl if self.cache_schema else 0,
            allowed_schemas=source_config["allowed_schemas"],
            allowed_tables=source_config["allowed_tables"],
            excluded_tables=source_config["excluded_tables"]
        )
        self._sql_executors[name] = SQLExecutor(
            max_results=self.max_results,
            allow_write=False,
            allowed_schemas=source_config["allowed_schemas"]
        )
        
        logger.info(f"已添加数据源: {name} - {source_config['description']}")
    
    def get_available_sources(self) -> Dict[str, str]:
        """获取可用的数据源列表"""
        return {name: config["description"] for name, config in self._sources.items()}
    
    def _convert_to_async_url(self, db_url: str) -> str:
        """
        将数据库 URL 转换为异步驱动 URL
        
        支持的转换：
        - mysql:// -> mysql+aiomysql://
        - mysql+pymysql:// -> mysql+aiomysql://
        - mysql+mysqlconnector:// -> mysql+aiomysql://
        - mysql+aiomysql:// -> 保持不变
        
        Args:
            db_url: 原始数据库 URL
            
        Returns:
            使用 aiomysql 驱动的异步 URL
        """
        # 匹配 mysql+任意驱动:// 或 mysql://
        pattern = r'^mysql(\+\w+)?://'
        match = re.match(pattern, db_url)
        
        if match:
            # 替换为 mysql+aiomysql://
            async_url = re.sub(pattern, 'mysql+aiomysql://', db_url)
            return async_url
        
        # 如果不是 mysql URL，原样返回
        logger.warning(f"未识别的数据库 URL 格式: {db_url[:50]}...")
        return db_url
    
    # ==================== 只读安全验证 ====================
    
    # 禁止的危险操作关键字
    DANGEROUS_KEYWORDS = [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", 
        "INSERT", "UPDATE", "REPLACE", "GRANT", "REVOKE",
        "RENAME", "EXECUTE", "CALL", "LOAD", "IMPORT",
        "SET", "LOCK", "UNLOCK", "KILL", "FLUSH"
    ]
    
    # 允许的只读操作
    ALLOWED_KEYWORDS = ["SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"]
    
    def _validate_readonly_sql(self, sql: str) -> tuple[bool, str]:
        """
        验证 SQL 是否为只读查询（兜底安全验证）
        
        这是在 SQLExecutor 验证之外的额外保护层，
        确保 LLM 生成的 SQL 不会意外执行危险操作。
        
        Args:
            sql: 待验证的 SQL 语句
            
        Returns:
            (是否安全, 错误信息)
        """
        if not sql or not sql.strip():
            return False, "SQL 语句不能为空"
        
        # 清理 SQL：移除注释和多余空格
        cleaned_sql = self._clean_sql_for_validation(sql)
        sql_upper = cleaned_sql.upper()
        
        # 检查是否以允许的关键字开头
        first_word = sql_upper.split()[0] if sql_upper.split() else ""
        
        if first_word not in self.ALLOWED_KEYWORDS:
            return False, f"只读模式：不允许执行 {first_word} 操作，仅支持 SELECT/SHOW/DESCRIBE/EXPLAIN"
        
        # 检查是否包含危险关键字
        for keyword in self.DANGEROUS_KEYWORDS:
            # 使用正则确保是完整单词匹配（避免误判如 "DELETED_AT" 字段名）
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                return False, f"只读模式：SQL 包含禁止的操作关键字 {keyword}"
        
        # 检查多语句执行风险
        if ';' in cleaned_sql:
            # 分号后还有内容（可能是多语句攻击）
            parts = [p.strip() for p in cleaned_sql.split(';') if p.strip()]
            if len(parts) > 1:
                return False, "只读模式：不允许执行多条 SQL 语句"
        
        # 检查常见 SQL 注入模式
        injection_patterns = [
            r";\s*--",           # 注释注入
            r";\s*DROP",         # DROP 注入
            r";\s*DELETE",       # DELETE 注入
            r";\s*INSERT",       # INSERT 注入
            r";\s*UPDATE",       # UPDATE 注入
            r"INTO\s+OUTFILE",   # 文件写入
            r"INTO\s+DUMPFILE",  # 文件写入
            r"LOAD_FILE\s*\(",   # 文件读取
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, sql_upper):
                return False, "只读模式：检测到潜在的危险操作"
        
        return True, ""
    
    def _clean_sql_for_validation(self, sql: str) -> str:
        """清理 SQL 用于安全验证"""
        # 移除单行注释
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        # 移除多行注释
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        # 移除多余空格
        sql = ' '.join(sql.split())
        return sql.strip()
    
    async def _get_session(self, source: Optional[str] = None) -> AsyncSession:
        """
        获取数据库会话
        
        Args:
            source: 数据源名称，不指定则使用默认数据源
        """
        source_name = source or self.default_source
        
        if source_name not in self._sources:
            raise ValueError(f"数据源 '{source_name}' 不存在，可用数据源: {list(self._sources.keys())}")
        
        # 懒加载引擎
        if source_name not in self._engines:
            db_url = self._sources[source_name]["url"]
            async_url = self._convert_to_async_url(db_url)
            logger.info(f"使用异步数据库连接: {async_url}")
            
            self._engines[source_name] = create_async_engine(
                async_url,
                echo=False,
                pool_size=5,
                max_overflow=10
            )
            self._session_factories[source_name] = sessionmaker(
                self._engines[source_name],
                class_=AsyncSession,
                expire_on_commit=False
            )
        
        return self._session_factories[source_name]()
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        schema = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的自然语言问题，例如：'查询最近7天的订单总额'、'统计各部门的员工人数'"
                },
                "tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选，指定要查询的表名列表。如果不指定，系统会自动推断相关表"
                },
                "schemas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选，指定要查询的数据库 schema 列表"
                },
                "execute": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否执行 SQL。设为 False 则只返回生成的 SQL 语句而不执行"
                },
                "explain_result": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否使用 LLM 解释查询结果"
                }
            },
            "required": ["question"]
        }
        
        # 如果有多个数据源，添加 source 参数
        if len(self._sources) > 1:
            source_descriptions = [f"{name}: {config['description']}" for name, config in self._sources.items()]
            schema["properties"]["source"] = {
                "type": "string",
                "enum": list(self._sources.keys()),
                "description": f"数据源名称。可选值：{'; '.join(source_descriptions)}。不指定则使用默认数据源 '{self.default_source}'"
            }
        
        return schema
    
    async def execute(
        self,
        question: str,
        source: Optional[str] = None,
        tables: Optional[List[str]] = None,
        schemas: Optional[List[str]] = None,
        execute: bool = True,
        explain_result: bool = True
    ) -> Dict[str, Any]:
        """
        执行 Text2SQL
        
        Args:
            question: 自然语言问题
            source: 数据源名称（多数据源时使用），不指定则使用默认数据源
            tables: 可选的表名列表
            schemas: 可选的 schema 列表
            execute: 是否执行 SQL
            explain_result: 是否解释结果
            
        Returns:
            {
                "success": True/False,
                "source": "使用的数据源名称",
                "sql": "生成的 SQL 语句",
                "data": [...],  # 查询结果
                "columns": [...],  # 列名
                "row_count": int,  # 行数
                "explanation": "结果解释",
                "error": str  # 错误信息（如果失败）
            }
        """
        # 确定使用的数据源
        source_name = source or self.default_source
        if source_name not in self._sources:
            return {
                "success": False,
                "error": f"数据源 '{source_name}' 不存在，可用数据源: {list(self._sources.keys())}",
                "question": question
            }
        # 获取对应数据源的组件
        schema_manager = self._schema_managers[source_name]
        sql_executor = self._sql_executors[source_name]
        
        session = None
        try:
            session = await self._get_session(source_name)
            
            # 1. 获取表结构信息
            logger.info(f"Text2SQL [{source_name}] 获取表结构信息...")
            schema_info = await schema_manager.get_schema_info(
                session=session,
                tables=tables,
                schemas=schemas,
                include_sample_data=self.include_sample_data
            )
            
            if "获取表结构信息失败" in schema_info or "未找到可用的表结构信息" in schema_info:
                return {
                    "success": False,
                    "source": source_name,
                    "error": schema_info,
                    "question": question
                }
            
            # 2. 使用 LLM 生成 SQL
            logger.info(f"Text2SQL [{source_name}] 生成 SQL: {question[:50]}...")
            sql = await self._generate_sql(question, schema_info, source_name)
            
            if not sql:
                return {
                    "success": False,
                    "source": source_name,
                    "error": "无法生成 SQL 语句",
                    "question": question
                }
            
            logger.info(f"生成的 SQL: {sql}")
            
            # 2.5. 只读安全验证（兜底保护）
            is_safe, error_msg = self._validate_readonly_sql(sql)
            if not is_safe:
                logger.warning(f"Text2SQL [{source_name}] SQL 安全验证失败: {error_msg}")
                return {
                    "success": False,
                    "source": source_name,
                    "sql": sql,
                    "error": error_msg,
                    "question": question
                }
            
            # 如果不需要执行，直接返回 SQL
            if not execute:
                return {
                    "success": True,
                    "source": source_name,
                    "sql": sql,
                    "data": None,
                    "row_count": 0,
                    "message": "SQL 已生成（已通过只读验证），未执行",
                    "question": question
                }
            
            # 3. 执行 SQL
            logger.info(f"Text2SQL [{source_name}] 执行查询...")
            result = await sql_executor.execute(session, sql)
            
            if not result.get("success"):
                # SQL 执行失败，尝试重新生成
                logger.warning(f"SQL 执行失败: {result.get('error')}，尝试重新生成...")
                sql = await self._regenerate_sql(question, schema_info, sql, result.get("error"))
                
                if sql:
                    result = await sql_executor.execute(session, sql)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "source": source_name,
                    "sql": sql,
                    "error": result.get("error"),
                    "question": question
                }
            
            # 4. 生成结果解释
            explanation = None
            if explain_result and result.get("data"):
                explanation = await self._generate_explanation(
                    question, sql, result.get("data"), result.get("row_count")
                )
            
            return {
                "success": True,
                "source": source_name,
                "sql": result.get("sql", sql),
                "data": result.get("data", []),
                "columns": result.get("columns", []),
                "row_count": result.get("row_count", 0),
                "explanation": explanation,
                "question": question
            }
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Text2SQL [{source_name}] 执行失败: {e}\n堆栈跟踪:\n{tb}")
            return {
                "success": False,
                "source": source_name,
                "error": str(e),
                "question": question
            }
        finally:
            if session:
                await session.close()
    
    async def _generate_sql(self, question: str, schema_info: str, source_name: Optional[str] = None) -> Optional[str]:
        """使用 LLM 生成 SQL"""
        # 添加数据源信息
        source_desc = ""
        if source_name and source_name in self._sources:
            source_desc = f"\n【当前数据源】\n{source_name}: {self._sources[source_name]['description']}\n"
        
        prompt = f"""你是一个专业的 SQL 专家。根据以下数据库表结构和用户的问题，生成准确的 MySQL **只读查询**语句。
{source_desc}
【数据库表结构】
{schema_info}

【用户问题】
{question}

【重要安全限制 - 只读模式】
⚠️ 本工具仅支持只读查询，严禁生成任何修改数据的 SQL！
- ✅ 允许：SELECT、SHOW、DESCRIBE、EXPLAIN
- ❌ 禁止：INSERT、UPDATE、DELETE、DROP、CREATE、ALTER、TRUNCATE 等任何修改操作
- 如果用户请求涉及数据修改，请拒绝并只返回 "READONLY_VIOLATION"

【要求】
1. 只返回 SELECT 查询语句，不要包含任何解释或 markdown 格式
2. 使用标准 MySQL 语法
3. 注意字段类型匹配，避免类型转换错误
4. 对于日期时间字段，使用合适的日期函数（如 DATE(), CURDATE(), DATE_SUB() 等）
5. 使用表别名提高可读性
6. 添加合理的 ORDER BY 排序
7. 如果涉及大量数据，添加 LIMIT 限制（默认不超过100条）
8. 使用反引号 `` 包裹表名和字段名，避免关键字冲突

【示例格式】
SELECT `column1`, `column2` FROM `schema`.`table` WHERE `condition` = 'value' ORDER BY `column1` LIMIT 100

SQL语句："""

        try:
            response = await self._call_llm(prompt)
            sql = self._clean_sql(response)
            
            # 检查 LLM 是否拒绝了请求
            if sql and "READONLY_VIOLATION" in sql.upper():
                logger.warning(f"Text2SQL: LLM 检测到用户请求涉及数据修改，已拒绝")
                return None
            
            return sql if sql else None
        except Exception as e:
            logger.error(f"生成 SQL 失败: {e}")
            return None
    
    async def _regenerate_sql(
        self,
        question: str,
        schema_info: str,
        failed_sql: str,
        error: str
    ) -> Optional[str]:
        """SQL 执行失败后重新生成"""
        prompt = f"""你是一个专业的 SQL 专家。之前生成的 SQL 执行失败了，请根据错误信息修正 SQL。

【数据库表结构】
{schema_info}

【用户问题】
{question}

【之前生成的 SQL】
{failed_sql}

【执行错误】
{error}

【重要安全限制 - 只读模式】
⚠️ 本工具仅支持只读查询，只能生成 SELECT 语句！

【要求】
1. 分析错误原因，修正 SQL 语句
2. 只返回修正后的 SELECT 查询语句，不要包含任何解释
3. 确保表名和字段名与表结构匹配
4. 使用反引号 `` 包裹表名和字段名
5. 严禁生成 INSERT/UPDATE/DELETE 等修改语句

修正后的 SQL："""

        try:
            response = await self._call_llm(prompt)
            sql = self._clean_sql(response)
            return sql if sql else None
        except Exception as e:
            logger.error(f"重新生成 SQL 失败: {e}")
            return None
    
    async def _generate_explanation(
        self,
        question: str,
        sql: str,
        data: List[Dict],
        row_count: int
    ) -> str:
        """生成查询结果解释"""
        # 限制数据量用于解释
        sample_data = data[:10] if len(data) > 10 else data
        data_str = json.dumps(sample_data, ensure_ascii=False, indent=2)
        
        prompt = f"""根据以下查询结果，用简洁的中文回答用户的问题。

【用户问题】
{question}

【执行的 SQL】
{sql}

【查询结果】（共 {row_count} 条记录，以下展示前 {len(sample_data)} 条）
{data_str}

【要求】
1. 直接回答用户的问题，不要重复问题
2. 如果结果为空，说明没有找到符合条件的数据
3. 如果有数值统计，给出具体数字
4. 语言简洁明了，像在和用户对话

回答："""

        try:
            response = await self._call_llm(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"生成解释失败: {e}")
            return f"查询成功，共返回 {row_count} 条记录"
    
    def _clean_sql(self, sql: str) -> str:
        """清理 SQL 语句"""
        if not sql:
            return ""
        
        # 移除 markdown 代码块
        sql = re.sub(r'```sql\s*\n?', '', sql)
        sql = re.sub(r'```\s*\n?', '', sql)
        
        # 移除开头的 "SQL语句：" 等前缀
        sql = re.sub(r'^(SQL语句|SQL|查询语句)[：:]\s*', '', sql, flags=re.IGNORECASE)
        
        # 移除单行注释
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        
        # 清理空白
        sql = sql.strip()
        
        return sql
    
    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        if hasattr(self.llm, 'ainvoke'):
            return await self.llm.ainvoke(prompt)
        elif hasattr(self.llm, '_call'):
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.llm._call, prompt)
        else:
            return self.llm._call(prompt)
    
    async def get_table_list(
        self,
        source: Optional[str] = None,
        schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取可用的表列表
        
        Args:
            source: 数据源名称
            schema: 指定的 schema
            
        Returns:
            表列表信息
        """
        source_name = source or self.default_source
        if source_name not in self._sources:
            return {
                "success": False,
                "error": f"数据源 '{source_name}' 不存在"
            }
        
        session = None
        try:
            session = await self._get_session(source_name)
            schema_manager = self._schema_managers[source_name]
            tables = await schema_manager.get_table_list(session, schema)
            
            return {
                "success": True,
                "source": source_name,
                "tables": tables,
                "count": len(tables)
            }
        except Exception as e:
            logger.error(f"获取表列表失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            if session:
                await session.close()
    
    def clear_schema_cache(self, source: Optional[str] = None, table_name: Optional[str] = None):
        """
        清除 Schema 缓存
        
        Args:
            source: 数据源名称，不指定则清除所有数据源的缓存
            table_name: 表名，不指定则清除该数据源的所有缓存
        """
        if source:
            if source in self._schema_managers:
                self._schema_managers[source].clear_cache(table_name)
        else:
            for schema_manager in self._schema_managers.values():
                schema_manager.clear_cache(table_name)
    
    async def cleanup(self):
        """清理所有数据源的资源"""
        for source_name, engine in self._engines.items():
            try:
                await engine.dispose()
                logger.debug(f"已关闭数据源 {source_name} 的连接")
            except Exception as e:
                logger.warning(f"关闭数据源 {source_name} 失败: {e}")
        
        self._engines.clear()
        self._session_factories.clear()

