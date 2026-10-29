#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/13 15:30
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
测试发送ASIN相关性分析任务到Redis队列

支持两种任务类型：

1. competitor_analysis - ASIN相关性分析
{
    "task_id": "xxx",
    "task_type": "competitor_analysis",
    "metadata": {
        "company_id": 10001,
        "site": "US",
        "main_asin": "B0F991FCCY",
        "spu": "GH-GTJ-010",
        "sub_asin": "B0CF5JQVCG",
        "retry": 0,
        "irrelevant_desc": ""
    }
}

2. keyword_analysis - 关键词相关性分析
{
    "task_id": "xxx",
    "task_type": "keyword_analysis",
    "metadata": {
        "company_id": 10001,
        "site": "US",
        "main_asin": "B0F991FCCY",
        "spu": "GH-GTJ-010",
        "keyword": "electric shaver",
        "keyword_root": "shaver",  # 可选字段，直接写入数据库
        "retry": 0,
        "irrelevant_desc": ""
    }
}
"""
import os
import json
import asyncio
import uuid
from typing import List, Dict, Any
from loguru import logger

try:
    import redis.asyncio as aioredis
except ImportError:
    logger.error("请安装redis库: pip install redis")
    raise

from dotenv import load_dotenv, find_dotenv

# 加载环境变量
load_dotenv(find_dotenv(".env", True), override=True)

# Redis配置
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_DB = int(os.getenv("REDIS_DB", "11"))

# 队列key
QUEUE_KEY = "ai:Ecomlinker:task_queue"


def build_task(metadata: Dict[str, Any], task_type: str = "competitor_analysis") -> Dict[str, Any]:
    """
    构建符合 task_parser.py 格式的任务
    
    Args:
        metadata: 元数据（包含 company_id, site, main_asin, spu, sub_asin/keyword, retry 等）
        task_type: 任务类型，可选 "competitor_analysis" 或 "keyword_analysis"
        
    Returns:
        完整的任务数据
    """
    if task_type == "keyword_analysis":
        keyword = metadata.get("keyword", "")
        task_id = f"keyword_analysis_{metadata['main_asin']}_{keyword}_{uuid.uuid4().hex[:8]}"
    else:
        sub_asin = metadata.get("sub_asin", "")
        task_id = f"asin_correlation_{metadata['main_asin']}_{sub_asin}_{uuid.uuid4().hex[:8]}"
    
    return {
        "task_id": task_id,
        "task_type": task_type,
        "metadata": metadata
    }


def build_keyword_task(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建关键词分析任务（便捷函数）
    
    Args:
        metadata: 元数据（包含 company_id, site, main_asin, spu, keyword, retry 等）
        
    Returns:
        完整的任务数据
    """
    return build_task(metadata, task_type="keyword_analysis")


async def send_task(redis_client: aioredis.Redis, task: Dict[str, Any]) -> bool:
    """
    发送单个任务到队列
    
    Args:
        redis_client: Redis客户端
        task: 任务数据（符合 task_parser.py 格式）
        
    Returns:
        是否发送成功
    """
    try:
        await redis_client.rpush(QUEUE_KEY, json.dumps(task, ensure_ascii=False))
        metadata = task.get("metadata", {})
        task_type = task.get("task_type", "unknown")
        
        if task_type == "keyword_analysis":
            logger.info(
                f"任务已发送: task_id={task['task_id']}, "
                f"task_type={task_type}, "
                f"main_asin={metadata.get('main_asin')}, keyword={metadata.get('keyword')}"
            )
        else:
            logger.info(
                f"任务已发送: task_id={task['task_id']}, "
                f"task_type={task_type}, "
                f"main_asin={metadata.get('main_asin')}, sub_asin={metadata.get('sub_asin')}"
            )
        return True
    except Exception as e:
        logger.error(f"发送任务失败: {e}")
        return False


async def send_batch_tasks(tasks: List[Dict[str, Any]]):
    """
    批量发送任务到Redis队列
    
    Args:
        tasks: 任务列表
    """
    # 连接Redis
    redis_client = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True
    )

    try:
        # 测试连接
        await redis_client.ping()
        logger.info(f"Redis连接成功: {REDIS_HOST}:{REDIS_PORT} db={REDIS_DB}")

        # 发送任务
        success_count = 0
        for task in tasks:
            if await send_task(redis_client, task):
                success_count += 1

        # 获取队列长度
        queue_len = await redis_client.llen(QUEUE_KEY)

        logger.info(f"发送完成: 成功 {success_count}/{len(tasks)}, 队列长度: {queue_len}")

    finally:
        await redis_client.aclose()


async def main():
    """主函数"""
    # 测试任务列表
    test_tasks = []
    competitor_metadata_list = []
    keyword_metadata_list = []

    # # 1. ASIN相关性分析任务（competitor_analysis）
    competitor_metadata_list = [
        {
            "company_id": 10001,
            "site": "US",
            "main_asin": "B0FF1RFQ3Z",
            "spu": "GH-GTJ-010",
            "sub_asin": "B0G3Q8FKCT",
            "retry": 0,
            "irrelevant_desc": ""
        },
    ]

    # 构建ASIN相关性分析任务
    for metadata in competitor_metadata_list:
        test_tasks.append(build_task(metadata, task_type="competitor_analysis"))
    
    # 2. 关键词相关性分析任务（keyword_analysis）
    # keyword_metadata_list = [
    #     {
    #         "company_id": 10001,
    #         "site": "US",
    #         "main_asin": "B0FY3L2SWP",
    #         "spu": "GH-GTJ-010",
    #         "keyword": "cord rotary razor man",
    #         "keyword_root": "trimmer",  # 可选字段，直接写入数据库
    #         "retry": 0,
    #         "irrelevant_desc": ""
    #     }
    # ]
    
    # 构建关键词相关性分析任务
    # for metadata in keyword_metadata_list:
    #     test_tasks.append(build_keyword_task(metadata))

    logger.info(f"准备发送 {len(test_tasks)} 个测试任务（包含 {len(competitor_metadata_list)} 个ASIN分析任务和 {len(keyword_metadata_list)} 个关键词分析任务）")
    await send_batch_tasks(test_tasks)


async def clear_queue():
    """清空队列（调试用）"""
    redis_client = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True
    )

    try:
        await redis_client.ping()
        deleted = await redis_client.delete(QUEUE_KEY)
        logger.info(f"队列已清空: {QUEUE_KEY}, 删除结果: {deleted}")
    finally:
        await redis_client.close()


async def check_queue():
    """查看队列状态"""
    redis_client = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True
    )

    try:
        await redis_client.ping()
        queue_len = await redis_client.llen(QUEUE_KEY)
        logger.info(f"队列长度: {queue_len}")

        # 查看前5个任务（不消费）
        if queue_len > 0:
            tasks = await redis_client.lrange(QUEUE_KEY, 0, min(4, queue_len - 1))
            logger.info("队列中的任务预览:")
            for i, task_str in enumerate(tasks):
                task = json.loads(task_str)
                metadata = task.get("metadata", {})
                task_type = task.get("task_type", "unknown")
                
                if task_type == "keyword_analysis":
                    logger.info(
                        f"  [{i + 1}] task_id={task.get('task_id')}, "
                        f"task_type={task_type}, "
                        f"main_asin={metadata.get('main_asin')}, "
                        f"keyword={metadata.get('keyword')}"
                    )
                else:
                    logger.info(
                        f"  [{i + 1}] task_id={task.get('task_id')}, "
                        f"task_type={task_type}, "
                        f"main_asin={metadata.get('main_asin')}, "
                        f"sub_asin={metadata.get('sub_asin')}"
                    )
    finally:
        await redis_client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试发送ASIN相关性分析任务（支持ASIN分析和关键词分析）")
    parser.add_argument("--action", choices=["send", "clear", "check"], default="send",
                        help="操作类型: send=发送测试任务, clear=清空队列, check=查看队列状态")

    args = parser.parse_args()

    if args.action == "send":
        asyncio.run(main())
    elif args.action == "clear":
        asyncio.run(clear_queue())
    elif args.action == "check":
        asyncio.run(check_queue())
