#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/12 17:55
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
ASIN相关性分析消费者
从Redis队列消费任务，支持两种任务类型：
1. competitor_analysis: 调用竞品分析Agent进行ASIN相似度分析
2. keyword_analysis: 调用关键词相关性识别Agent进行关键词与ASIN的相关性分析
"""
import os
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from core.llm import OpenAIGPTLLM
from sqlalchemy import text

from agent_applications.task_agents.competitor_analysis_agent import CompetitorAnalysisAgent
from agent_applications.task_agents.keyword_relevance_agent import KeywordRelevanceAgent

# 导入基类和配置
from consumers.base_consumer import (
    BaseConsumer,
    RedisConfig,
    DBConfig,
    ConsumerConfig
)


@dataclass
class ASINCorrelationConsumerConfig(ConsumerConfig):
    """ASIN相关性分析消费者配置"""
    queue_key: str = field(default_factory=lambda: os.getenv("ASIN_CORRELATION_QUEUE_KEY", "ai:Ecomlinker:task_queue"))
    result_key_prefix: str = field(default_factory=lambda: os.getenv("ASIN_CORRELATION_RESULT_PREFIX", "ai:Ecomlinker:asin_correlation:result:"))
    poll_interval: float = field(default_factory=lambda: float(os.getenv("ASIN_CORRELATION_POLL_INTERVAL", "1.0")))
    batch_size: int = field(default_factory=lambda: int(os.getenv("ASIN_CORRELATION_BATCH_SIZE", "1")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("ASIN_CORRELATION_MAX_RETRIES", "3")))
    worker_count: int = field(default_factory=lambda: int(os.getenv("ASIN_CORRELATION_WORKER_COUNT", "3")))
    task_timeout: int = field(default_factory=lambda: int(os.getenv("ASIN_CORRELATION_TASK_TIMEOUT", "120")))


@dataclass
class CrawlerDBConfig(DBConfig):
    """爬虫数据库配置（用于查询ASIN信息）"""
    host: str = field(default_factory=lambda: os.getenv("CRAWLER_MYSQL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("CRAWLER_MYSQL_PORT", "3306")))
    username: str = field(default_factory=lambda: os.getenv("CRAWLER_MYSQL_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("CRAWLER_MYSQL_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.getenv("CRAWLER_MYSQL_DB", ""))


@dataclass
class ResultDBConfig(DBConfig):
    """结果数据库配置（用于写入分析结果）"""
    host: str = field(default_factory=lambda: os.getenv("PUCHEN_MYSQL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("PUCHEN_MYSQL_PORT", "3306")))
    username: str = field(default_factory=lambda: os.getenv("PUCHEN_MYSQL_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("PUCHEN_MYSQL_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.getenv("PUCHEN_MYSQL_DB", ""))


@dataclass
class TaskData:
    """
    任务数据模型
    
    支持两种任务类型：
    1. competitor_analysis - ASIN相关性分析
    2. keyword_analysis - 关键词相关性分析
    
    消息格式（符合 task_parser.py）：
    {
        "task_id": "xxx",
        "task_type": "competitor_analysis" | "keyword_analysis",
        "metadata": {
            "company_id": 10001,
            "site": "US",
            "main_asin": "B0F991FCCY",
            "spu": "GH-GTJ-010",
            "sub_asin": "B0CF5JQVCG",  # competitor_analysis 使用
            "keyword": "B0CF5JQVCG",   # keyword_analysis 使用
            "keyword_root": "root_keyword",  # keyword_analysis 使用，直接写入数据库
            "retry": 0,
            "irrelevant_desc": ""
        }
    }
    """
    task_id: str
    task_type: str
    company_id: int
    site: str
    main_asin: str
    spu: str
    sub_asin: Optional[str] = None  # competitor_analysis 使用
    keyword: Optional[str] = None    # keyword_analysis 使用
    keyword_root: Optional[str] = None  # keyword_analysis 使用，直接写入数据库
    retry: int = 0
    irrelevant_desc: str = ""
    
    @classmethod
    def from_message(cls, message: Dict[str, Any]) -> "TaskData":
        """
        从消息创建任务数据（符合 task_parser.py 格式）
        
        Args:
            message: 完整的消息，包含 task_id, task_type, metadata
        """
        task_id = message.get("task_id", "")
        task_type = message.get("task_type", "")
        metadata = message.get("metadata", {})
        
        return cls(
            task_id=task_id,
            task_type=task_type,
            company_id=int(metadata.get("company_id", 0)),
            site=str(metadata.get("site", "")),
            main_asin=str(metadata.get("main_asin", "")),
            spu=str(metadata.get("spu", "")),
            sub_asin=metadata.get("sub_asin"),  # 可能为 None（keyword_analysis 任务）
            keyword=metadata.get("keyword"),    # 可能为 None（competitor_analysis 任务）
            keyword_root=metadata.get("keyword_root"),  # keyword_analysis 使用，可能为 None
            retry=int(metadata.get("retry", 0)),
            irrelevant_desc=str(metadata.get("irrelevant_desc", ""))
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（metadata格式）"""
        result = {
            "company_id": self.company_id,
            "site": self.site,
            "main_asin": self.main_asin,
            "spu": self.spu,
            "retry": self.retry,
            "irrelevant_desc": self.irrelevant_desc
        }
        # 根据任务类型添加相应字段
        if self.task_type == "competitor_analysis" and self.sub_asin:
            result["sub_asin"] = self.sub_asin
        elif self.task_type == "keyword_analysis":
            if self.keyword:
                result["keyword"] = self.keyword
            if self.keyword_root:
                result["keyword_root"] = self.keyword_root
        return result
    
    def to_message(self) -> Dict[str, Any]:
        """转换为完整消息格式（用于重试）"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "metadata": self.to_dict()
        }
    
    def __str__(self) -> str:
        """字符串表示（用于日志）"""
        if self.task_type == "keyword_analysis":
            return f"main_asin={self.main_asin}, keyword={self.keyword}, site={self.site}"
        else:
            return f"main_asin={self.main_asin}, sub_asin={self.sub_asin}, site={self.site}"


class ASINCorrelationAnalysisConsumer(BaseConsumer[TaskData]):
    """ASIN相关性分析消费者"""
    
    # 结果映射：中文 -> 英文枚举值
    RESULT_MAPPING = {
        "强相关": "Strongly Related",
        "低相关": "Weakly Related",
        "不相关": "Unrelated",
    }
    
    def __init__(
        self,
        redis_config: Optional[RedisConfig] = None,
        db_config: Optional[CrawlerDBConfig] = None,
        result_db_config: Optional[ResultDBConfig] = None,
        consumer_config: Optional[ASINCorrelationConsumerConfig] = None,
        llm_api_key: Optional[str] = None
    ):
        """
        初始化消费者
        
        Args:
            redis_config: Redis配置
            db_config: 爬虫数据库配置（用于查询ASIN信息）
            result_db_config: 结果数据库配置（用于写入分析结果）
            consumer_config: 消费者配置（默认使用ASINCorrelationConsumerConfig）
            llm_api_key: LLM API密钥
        """
        # 准备数据库配置字典
        db_configs = {}
        if db_config:
            db_configs["crawler"] = db_config
        if result_db_config:
            db_configs["result"] = result_db_config
        
        # 使用默认配置或传入的配置
        if consumer_config is None:
            consumer_config = ASINCorrelationConsumerConfig()
        
        # 调用基类初始化
        super().__init__(
            redis_config=redis_config,
            consumer_config=consumer_config,
            db_configs=db_configs
        )
        
        # 保存配置引用（用于向后兼容）
        self.db_config = db_config or CrawlerDBConfig()
        self.result_db_config = result_db_config or ResultDBConfig()
        
        # LLM和Agent
        api_key = llm_api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("未配置OPENAI_API_KEY")
        
        self.llm = OpenAIGPTLLM(
            api_key=api_key,
            model_name='gpt-5.2',
            max_completion_tokens = 4096,
            temperature=0.3
        )

        logger.info(f'现在使用的是{self.llm.model_name}')
        
        # 使用标准版竞品分析Agent（返回完整分析结果）
        logger.info("使用标准版竞品分析Agent（返回完整分析结果）")
        self.agent = CompetitorAnalysisAgent(
            agent_name="ASIN相关性分析Agent",
            llm=self.llm
        )
        
        # 初始化关键词相关性识别Agent（用于 keyword_analysis）
        self.keyword_agent = KeywordRelevanceAgent(
            agent_name="关键词相关性识别Agent",
            llm=self.llm
        )
    
    async def _custom_initialize(self) -> bool:
        """子类特定的初始化"""
        # 初始化竞品分析Agent
        if not await self.agent.initialize():
            logger.error("竞品分析Agent初始化失败")
            return False
        
        # 初始化关键词相关性识别Agent
        if not await self.keyword_agent.initialize():
            logger.error("关键词相关性识别Agent初始化失败")
            return False
        
        # 启动 LLM 使用量追踪器 Worker（确保消费者调用的 LLM 使用记录能入库）
        try:
            from core.llm.base.usage_tracker import get_usage_tracker
            usage_tracker = get_usage_tracker()
            await usage_tracker.start_worker()
            logger.info("LLM 使用量追踪器 Worker 已启动")
        except Exception as e:
            logger.warning(f"启动 LLM 使用量追踪器 Worker 失败: {e}", exc_info=True)
        
        # 从数据库加载模型费用配置到 CostCalculator（确保 gpt-5.2 等 DB 中的配置可用）
        try:
            from core.llm.base.cost_calculator import load_pricing_from_database
            await load_pricing_from_database()
        except Exception as e:
            logger.warning(f"加载模型费用配置失败: {e}", exc_info=True)
        
        return True
    
    async def _custom_cleanup(self):
        """子类特定的清理"""
        # 先 flush LLM 使用记录，再停止 Worker
        try:
            from core.llm.base.usage_tracker import get_usage_tracker
            usage_tracker = get_usage_tracker()
            await usage_tracker.flush_now_async()
            await usage_tracker.stop_worker()
            logger.info("LLM 使用量追踪器已停止并刷新剩余记录")
        except Exception as e:
            logger.warning(f"停止 LLM 使用量追踪器失败: {e}", exc_info=True)
        
        await self.agent.cleanup()
        await self.keyword_agent.cleanup()
    
    # ==================== 实现抽象方法 ====================
    
    def parse_task_message(self, message: Dict[str, Any]) -> Optional[TaskData]:
        """解析任务消息为任务数据对象"""
        try:
            return TaskData.from_message(message)
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"解析任务消息失败: {e}, 消息: {message}")
            return None
    
    async def process_task(self, task: TaskData):
        """处理任务（核心业务逻辑）"""
        # 根据任务类型路由到不同的处理逻辑
        if task.task_type == "keyword_analysis":
            await self._process_keyword_analysis_task(task)
        else:
            # 默认处理 competitor_analysis 任务
            await self._process_competitor_analysis_task(task)
    
    async def _process_competitor_analysis_task(self, task: TaskData):
        """处理ASIN相关性分析任务"""
        # 0. 检查是否已存在结果（去重机制，节省大模型成本）
        existing_result = await self._check_existing_result(task)
        if existing_result:
            logger.info(
                f"任务已存在结果（跳过Agent调用）: {task.main_asin} vs {task.sub_asin}, "
                f"相关性: {existing_result.get('similarity_analysis_result', '未知')}"
            )
            # 直接保存现有结果（更新Redis缓存）
            await self.save_result(task, existing_result)
            return
        
        # 1. 查询两个ASIN的信息
        main_asin_info = await self._query_asin_info(task.main_asin, task.site)
        sub_asin_info = await self._query_asin_info(task.sub_asin, task.site)
        
        if not main_asin_info:
            raise ValueError(f"主ASIN信息不存在: {task.main_asin}")
        
        if not sub_asin_info:
            raise ValueError(f"子ASIN信息不存在: {task.sub_asin}")
        
        # 2. 调用竞品分析Agent
        analysis_result = await self._analyze_asin_correlation(
            main_asin_info, sub_asin_info, task
        )
        
        # 3. 保存结果
        await self.save_result(task, analysis_result)
        
        logger.info(
            f"任务完成: {task.main_asin} vs {task.sub_asin}, "
            f"相关性: {analysis_result.get('similarity_analysis_result', '未知')}"
        )
    
    async def _process_keyword_analysis_task(self, task: TaskData):
        """处理关键词相关性分析任务"""
        # 0. 检查是否已存在结果（去重机制，节省大模型成本）
        existing_result = await self._check_keyword_existing_result(task)
        if existing_result:
            logger.info(
                f"任务已存在结果（跳过Agent调用）: {task.main_asin} vs keyword={task.keyword}, "
                f"相关性: {existing_result.get('relevance_result', '未知')}"
            )
            # 直接保存现有结果（更新Redis缓存）
            await self.save_result(task, existing_result)
            return
        
        # 1. 查询主ASIN的信息
        main_asin_info = await self._query_asin_info(task.main_asin, task.site)
        
        if not main_asin_info:
            raise ValueError(f"主ASIN信息不存在: {task.main_asin}")
        
        if not task.keyword:
            raise ValueError("关键词不能为空")
        
        # 2. 调用关键词相关性识别Agent
        analysis_result = await self._analyze_keyword_relevance(
            main_asin_info, task.keyword, task
        )
        
        # 3. 保存结果
        await self.save_result(task, analysis_result)
        
        logger.info(
            f"任务完成: {task.main_asin} vs keyword={task.keyword}, "
            f"相关性: {analysis_result.get('relevance_result', '未知')}"
        )
    
    def get_retry_count(self, task: TaskData) -> int:
        """获取任务的重试次数"""
        return task.retry
    
    def increment_retry(self, task: TaskData) -> TaskData:
        """增加任务的重试次数并返回新任务对象"""
        # 创建新对象，retry+1
        return TaskData(
            task_id=task.task_id,
            task_type=task.task_type,
            company_id=task.company_id,
            site=task.site,
            main_asin=task.main_asin,
            spu=task.spu,
            sub_asin=task.sub_asin,
            keyword=task.keyword,
            keyword_root=task.keyword_root,
            retry=task.retry + 1,
            irrelevant_desc=task.irrelevant_desc
        )
    
    def task_to_message(self, task: TaskData) -> Dict[str, Any]:
        """将任务对象转换为消息格式（用于重试时重新入队）"""
        return task.to_message()
    
    # ==================== 业务逻辑方法 ====================
    
    async def _check_keyword_existing_result(self, task: TaskData) -> Optional[Dict[str, Any]]:
        """
        检查数据库中是否已存在该关键词的分析结果（去重机制）
        
        Args:
            task: 任务数据
            
        Returns:
            如果存在结果，返回结果字典；否则返回None
        """
        # 如果关键词为空，直接返回None
        if not task.keyword:
            return None
        
        try:
            async with self.get_session("result") as session:
                query = text("""
                    SELECT result, reasoning, confidence, updated_at
                    FROM puchen_sys_erp.product_keyword_relations
                    WHERE site = :site 
                      AND main_asin = :main_asin 
                      AND keyword = :keyword
                    LIMIT 1
                """)
                
                result = await session.execute(query, {
                    "site": task.site,
                    "main_asin": task.main_asin,
                    "keyword": task.keyword
                })
                row = result.fetchone()
                
                if row:
                    # 将数据库枚举值映射回中文
                    db_result = row.result
                    reverse_mapping = {
                        "Strongly Related": "高相关",
                        "Weakly Related": "低相关",
                        "Unrelated": "不相关",
                        "Not Available": None
                    }
                    relevance_result = reverse_mapping.get(db_result, None)
                    
                    # 构建结果字典（与_analyze_keyword_relevance返回格式一致）
                    existing_result = {
                        "confidence": float(row.confidence) if row.confidence is not None else 0.0,
                        "reasoning": str(row.reasoning) if row.reasoning else "",
                        "relevance_result": relevance_result,
                        "main_asin": task.main_asin,
                        "keyword": task.keyword,
                        "site": task.site,
                        "company_id": task.company_id,
                        "spu": task.spu,
                        "from_cache": True  # 标记为缓存结果
                    }
                    
                    logger.debug(
                        f"找到已存在结果: {task.main_asin} vs keyword={task.keyword} -> {db_result}"
                    )
                    return existing_result
                
                return None
                
        except Exception as e:
            logger.error(
                f"检查已存在结果失败: {task.main_asin} vs keyword={task.keyword}, 错误: {e}"
            )
            # 检查失败时返回None，继续执行Agent分析（容错处理）
            return None
    
    async def _check_existing_result(self, task: TaskData) -> Optional[Dict[str, Any]]:
        """
        检查数据库中是否已存在该ASIN对的分析结果（去重机制）
        
        Args:
            task: 任务数据
            
        Returns:
            如果存在结果，返回结果字典；否则返回None
        """
        try:
            async with self.get_session("result") as session:
                query = text("""
                    SELECT result, reasoning, is_competitor, confidence, updated_at
                    FROM puchen_sys_erp.product_relations
                    WHERE site = :site 
                      AND main_asin = :main_asin 
                      AND sub_asin = :sub_asin
                    LIMIT 1
                """)
                
                result = await session.execute(query, {
                    "site": task.site,
                    "main_asin": task.main_asin,
                    "sub_asin": task.sub_asin
                })
                row = result.fetchone()
                
                if row:
                    # 将数据库枚举值映射回中文
                    db_result = row.result
                    reverse_mapping = {
                        "Strongly Related": "强相关",
                        "Weakly Related": "低相关",
                        "Unrelated": "不相关",
                        "Not Available": None
                    }
                    similarity_result = reverse_mapping.get(db_result, None)
                    
                    # 构建结果字典（与_analyze_asin_correlation返回格式一致）
                    existing_result = {
                        "is_competitor": row.is_competitor,
                        "confidence": float(row.confidence) if row.confidence is not None else 0.0,
                        "reasoning": str(row.reasoning) if row.reasoning else "",
                        "similarity_analysis": {},  # 数据库中没有存储详细分析
                        "similarity_analysis_result": similarity_result,
                        "main_asin": task.main_asin,
                        "sub_asin": task.sub_asin,
                        "site": task.site,
                        "company_id": task.company_id,
                        "spu": task.spu,
                        "from_cache": True  # 标记为缓存结果
                    }
                    
                    logger.debug(
                        f"找到已存在结果: {task.main_asin} vs {task.sub_asin} -> {db_result}"
                    )
                    return existing_result
                
                return None
                
        except Exception as e:
            logger.error(
                f"检查已存在结果失败: {task.main_asin} vs {task.sub_asin}, 错误: {e}"
            )
            # 检查失败时返回None，继续执行Agent分析（容错处理）
            return None
    
    async def _query_asin_info(self, asin: str, site: str) -> Optional[Dict[str, Any]]:
        """
        查询ASIN信息
        
        Args:
            asin: ASIN编码
            site: 站点
            
        Returns:
            ASIN信息字典，包含title和bullet_points
        """
        try:
            async with self.get_session("crawler") as session:
                query = text("""
                    SELECT asin, site, title, bullet_points, brand, first_img
                    FROM amazon_asin_crawl_detail
                    WHERE asin = :asin AND site = :site
                    ORDER BY update_time DESC
                    LIMIT 1
                """)
                
                result = await session.execute(
                    query,
                    {"asin": asin, "site": site}
                )
                row = result.fetchone()
                
                if row:
                    return {
                        "asin": row.asin,
                        "site": row.site,
                        "title": row.title or "",
                        "description": row.bullet_points or "",  # 使用五点描述作为描述
                        "brand": row.brand or "",
                        "first_img": row.first_img or ""
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"查询ASIN信息失败: {asin}, {site}, 错误: {e}")
            return None
    
    async def _analyze_keyword_relevance(
        self,
        main_asin_info: Dict[str, Any],
        keyword: str,
        task: TaskData
    ) -> Dict[str, Any]:
        """
        分析关键词与ASIN的相关性
        
        Args:
            main_asin_info: 主ASIN信息
            keyword: 关键词
            task: 任务数据
            
        Returns:
            分析结果
        """
        # 构建Agent任务
        agent_task = {
            "keyword": keyword,
            "product": {
                "title": main_asin_info.get("title", ""),
                "description": main_asin_info.get("description", "")
            },
            "task_id": f"keyword_analysis_{task.main_asin}_{keyword}"
        }
        
        # 执行分析
        result = await self.keyword_agent.execute(agent_task)
        
        # 提取结果
        if isinstance(result, dict):
            # 结果可能在result字段中，也可能直接在顶层
            if "result" in result and isinstance(result["result"], dict):
                analysis_result = result["result"]
            else:
                analysis_result = result
            
            # 获取 relevance_result，保持 None 如果是 None
            relevance_result = analysis_result.get("relevance_result")
            
            return {
                "confidence": 0.0,  # 关键词分析暂不提供置信度
                "reasoning": "",    # 关键词分析暂不提供详细推理
                "relevance_result": relevance_result,  # 保持原值，可能是 None
                "main_asin": task.main_asin,
                "keyword": keyword,
                "keyword_root": task.keyword_root,
                "site": task.site,
                "company_id": task.company_id,
                "spu": task.spu
            }
        
        return {
            "confidence": 0.0,
            "reasoning": "分析结果格式异常",
            "relevance_result": None,  # None 表示分析失败，入库为 Not Available
            "main_asin": task.main_asin,
            "keyword": keyword,
            "keyword_root": task.keyword_root,
            "site": task.site,
            "company_id": task.company_id,
            "spu": task.spu,
            "error": "分析结果格式异常"
        }
    
    async def _analyze_asin_correlation(
        self,
        main_asin_info: Dict[str, Any],
        sub_asin_info: Dict[str, Any],
        task: TaskData
    ) -> Dict[str, Any]:
        """
        分析两个ASIN的相关性
        
        Args:
            main_asin_info: 主ASIN信息
            sub_asin_info: 子ASIN信息
            task: 任务数据
            
        Returns:
            分析结果
        """
        # 构建Agent任务
        agent_task = {
            "product1": {
                "title": main_asin_info.get("title", ""),
                "description": main_asin_info.get("description", "")
            },
            "product2": {
                "title": sub_asin_info.get("title", ""),
                "description": sub_asin_info.get("description", "")
            },
            "thinking_mode": "normal",
            "task_id": f"asin_correlation_{task.main_asin}_{task.sub_asin}"
        }
        
        # 执行分析
        result = await self.agent.execute(agent_task)
        
        # 提取结果
        if isinstance(result, dict):
            # 结果可能在result字段中，也可能直接在顶层
            if "result" in result and isinstance(result["result"], dict):
                analysis_result = result["result"]
            else:
                analysis_result = result
            
            # 获取 similarity_analysis_result，保持 None 如果是 None
            similarity_result = analysis_result.get("similarity_analysis_result")
            
            # 返回完整分析结果
            return {
                "is_competitor": analysis_result.get("is_competitor"),  # 可能是 None
                "confidence": float(analysis_result.get("confidence", 0.0)),
                "reasoning": str(analysis_result.get("reasoning", "")),
                "similarity_analysis": analysis_result.get("similarity_analysis", {}),
                "similarity_analysis_result": similarity_result,  # 保持原值，可能是 None
                    "main_asin": task.main_asin,
                    "sub_asin": task.sub_asin,
                    "site": task.site,
                    "company_id": task.company_id,
                    "spu": task.spu
                }
        
        return {
            "is_competitor": None,
            "confidence": 0.0,
            "reasoning": "分析结果格式异常",
            "similarity_analysis": {},
            "similarity_analysis_result": None,  # None 表示分析失败，入库为 Not Available
            "main_asin": task.main_asin,
            "sub_asin": task.sub_asin,
            "site": task.site,
            "company_id": task.company_id,
            "spu": task.spu,
            "error": "分析结果格式异常"
        }
    
    def _map_result_to_enum(self, similarity_result: Optional[str]) -> str:
        """
        将中文相关性结果映射为数据库枚举值
        
        Args:
            similarity_result: 中文相关性结果（强相关/低相关/不相关），None表示分析失败
            
        Returns:
            数据库枚举值（Strongly Related/Weakly Related/Unrelated/Not Available）
        """
        if similarity_result is None:
            return "Not Available"
        return self.RESULT_MAPPING.get(similarity_result, "Not Available")
    
    def _map_keyword_result_to_enum(self, relevance_result: Optional[str]) -> str:
        """
        将关键词相关性结果映射为数据库枚举值
        
        Args:
            relevance_result: 中文相关性结果（高相关/低相关/不相关），None表示分析失败
            
        Returns:
            数据库枚举值（Strongly Related/Weakly Related/Unrelated/Not Available）
        """
        if relevance_result is None:
            return "Not Available"
        # 关键词分析的结果映射：高相关->Strongly Related, 低相关->Weakly Related, 不相关->Unrelated
        keyword_mapping = {
            "高相关": "Strongly Related",
            "低相关": "Weakly Related",
            "不相关": "Unrelated"
        }
        return keyword_mapping.get(relevance_result, "Not Available")
    
    async def save_result(self, task: TaskData, result: Dict[str, Any]):
        """
        保存分析结果（覆盖基类方法，添加数据库保存）
        
        Args:
            task: 任务数据
            result: 分析结果
        """
        try:
            # 1. 保存到Redis（调用基类方法）
            await super().save_result(task, result)
            
            # 2. 根据任务类型保存到不同的数据库表
            if task.task_type == "keyword_analysis":
                await self._save_keyword_result_to_database(task, result)
            else:
                # 默认保存到 product_relations 表
                await self._save_result_to_database(task, result)
            
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
    
    async def _save_keyword_result_to_database(self, task: TaskData, result: Dict[str, Any]):
        """
        将关键词分析结果写入数据库 product_keyword_relations 表
        
        Args:
            task: 任务数据
            result: 分析结果
        """
        try:
            # 映射结果到数据库枚举值
            relevance_result = result.get("relevance_result")
            db_result = self._map_keyword_result_to_enum(relevance_result)
            
            # 提取需要保存的字段
            reasoning = result.get("reasoning", "")
            confidence = result.get("confidence", 0.0)
            
            async with self.get_session("result") as session:
                # 使用 INSERT ... ON DUPLICATE KEY UPDATE 实现 upsert
                query = text("""
                    INSERT INTO puchen_sys_erp.product_keyword_relations 
                        (site, company_id, main_asin, keyword, keyword_root, result, reasoning, confidence)
                    VALUES 
                        (:site, :company_id, :main_asin, :keyword, :keyword_root, :result, :reasoning, :confidence)
                    ON DUPLICATE KEY UPDATE
                        site = VALUES(site),
                        company_id = VALUES(company_id),
                        keyword_root = VALUES(keyword_root),
                        result = VALUES(result),
                        reasoning = VALUES(reasoning),
                        confidence = VALUES(confidence),
                        updated_at = CURRENT_TIMESTAMP
                """)
                
                await session.execute(query, {
                    "site": task.site,
                    "company_id": str(task.company_id) if task.company_id else None,
                    "main_asin": task.main_asin,
                    "keyword": task.keyword,
                    "keyword_root": task.keyword_root if task.keyword_root else None,
                    "result": db_result,
                    "reasoning": reasoning if reasoning else None,
                    "confidence": float(confidence) if confidence is not None else None
                })
                
                await session.commit()
                
            logger.info(
                f"数据库结果已保存: {task.main_asin} vs keyword={task.keyword} -> {db_result}, "
                f"confidence={confidence}"
            )
            
        except Exception as e:
            logger.error(f"写入数据库失败: {e}", exc_info=True)
    
    async def _save_result_to_database(self, task: TaskData, result: Dict[str, Any]):
        """
        将分析结果写入数据库 product_relations 表
        
        Args:
            task: 任务数据
            result: 分析结果
        """
        try:
            # 映射结果到数据库枚举值
            similarity_result = result.get("similarity_analysis_result")
            db_result = self._map_result_to_enum(similarity_result)
            
            # 提取需要保存的字段
            reasoning = result.get("reasoning", "")
            is_competitor = result.get("is_competitor")
            confidence = result.get("confidence", 0.0)
            
            async with self.get_session("result") as session:
                # 使用 INSERT ... ON DUPLICATE KEY UPDATE 实现 upsert
                query = text("""
                    INSERT INTO puchen_sys_erp.product_relations 
                        (site, company_id, spu, main_asin, sub_asin, result, reasoning, is_competitor, confidence)
                    VALUES 
                        (:site, :company_id, :spu, :main_asin, :sub_asin, :result, :reasoning, :is_competitor, :confidence)
                    ON DUPLICATE KEY UPDATE
                        site = VALUES(site),
                        company_id = VALUES(company_id),
                        spu = VALUES(spu),
                        result = VALUES(result),
                        reasoning = VALUES(reasoning),
                        is_competitor = VALUES(is_competitor),
                        confidence = VALUES(confidence),
                        updated_at = CURRENT_TIMESTAMP
                """)
                
                await session.execute(query, {
                    "site": task.site,
                    "company_id": str(task.company_id) if task.company_id else None,
                    "spu": task.spu if task.spu else None,
                    "main_asin": task.main_asin,
                    "sub_asin": task.sub_asin,
                    "result": db_result,
                    "reasoning": reasoning if reasoning else None,
                    "is_competitor": is_competitor if is_competitor is not None else None,
                    "confidence": float(confidence) if confidence is not None else None
                })
                
                await session.commit()
                
            logger.info(
                f"数据库结果已保存: {task.main_asin} vs {task.sub_asin} -> {db_result}, "
                f"is_competitor={is_competitor}, confidence={confidence}"
            )
            
        except Exception as e:
            logger.error(f"写入数据库失败: {e}", exc_info=True)
    
    async def save_failure_result(self, task: TaskData, error_msg: str):
        """
        保存失败结果（覆盖基类方法，添加数据库保存）
        
        Args:
            task: 任务数据
            error_msg: 错误信息
        """
        if task.task_type == "keyword_analysis":
            failure_result = {
                "confidence": 0.0,
                "reasoning": f"任务失败: {error_msg}",
                "relevance_result": None,  # None 表示分析失败，入库为 Not Available
                "main_asin": task.main_asin,
                "keyword": task.keyword,
                "keyword_root": task.keyword_root,
                "site": task.site,
                "company_id": task.company_id,
                "spu": task.spu,
                "error": error_msg,
                "failed": True
            }
        else:
            failure_result = {
                "is_competitor": None,
                "confidence": 0.0,
                "reasoning": f"任务失败: {error_msg}",
                "similarity_analysis": {},
                "similarity_analysis_result": None,  # None 表示分析失败，入库为 Not Available
                "main_asin": task.main_asin,
                "sub_asin": task.sub_asin,
                "site": task.site,
                "company_id": task.company_id,
                "spu": task.spu,
                "error": error_msg,
                "failed": True
            }
        await self.save_result(task, failure_result)


async def run_asin_correlation_consumer(
    redis_password: Optional[str] = None,
    db_host: Optional[str] = None,
    db_port: Optional[int] = None,
    db_username: Optional[str] = None,
    db_password: Optional[str] = None,
    db_name: Optional[str] = None,
    worker_count: int = 3
):
    """
    运行ASIN相关性分析消费者
    
    Args:
        redis_password: Redis密码
        db_host: 数据库主机
        db_port: 数据库端口
        db_username: 数据库用户名
        db_password: 数据库密码
        db_name: 数据库名
        worker_count: 工作线程数
        fast_mode: 是否使用极速版Agent（只返回similarity_analysis_result，速度更快）
    """
    # 配置（Redis配置从.env读取）
    redis_config = RedisConfig()
    if redis_password:
        redis_config.password = redis_password
    
    db_config = CrawlerDBConfig()
    if db_host:
        db_config.host = db_host
    if db_port:
        db_config.port = db_port
    if db_username:
        db_config.username = db_username
    if db_password:
        db_config.password = db_password
    if db_name:
        db_config.database = db_name
    
    result_db_config = ResultDBConfig()
    
    consumer_config = ASINCorrelationConsumerConfig(
        worker_count=worker_count
    )
    
    # 创建消费者
    consumer = ASINCorrelationAnalysisConsumer(
        redis_config=redis_config,
        db_config=db_config,
        result_db_config=result_db_config,
        consumer_config=consumer_config,
        fast_mode=fast_mode
    )
    
    # 初始化
    if not await consumer.initialize():
        logger.error("消费者初始化失败")
        return
    
    # 启动
    await consumer.start()
    
    logger.info("消费者正在运行，按 Ctrl+C 停止...")
    
    try:
        # 保持运行
        while True:
            await asyncio.sleep(60)
            # 定期打印健康状态
            health = await consumer.health_check()
            queue_len = await consumer.get_queue_length()
            logger.info(
                f"健康状态: {health['healthy']}, "
                f"队列长度: {queue_len}, "
                f"已处理: {consumer.stats['total_consumed']}"
            )
    except asyncio.CancelledError:
        pass
    finally:
        await consumer.stop()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ASIN相关性分析消费者")
    parser.add_argument("--redis-password", help="Redis密码（默认从.env的REDIS_PASSWORD读取）")
    parser.add_argument("--db-host", help="数据库主机")
    parser.add_argument("--db-port", type=int, help="数据库端口")
    parser.add_argument("--db-username", help="数据库用户名")
    parser.add_argument("--db-password", help="数据库密码")
    parser.add_argument("--db-name", help="数据库名")
    parser.add_argument("--workers", type=int, default=1, help="工作线程数")
    parser.add_argument("--fast-mode", action="store_true", help="使用极速版Agent（只返回similarity_analysis_result，速度更快）")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_asin_correlation_consumer(
            redis_password=args.redis_password,
            db_host=args.db_host,
            db_port=args.db_port,
            db_username=args.db_username,
            db_password=args.db_password,
            db_name=args.db_name,
            worker_count=args.workers,
            fast_mode=True
        ))
    except KeyboardInterrupt:
        logger.info("收到退出信号")
