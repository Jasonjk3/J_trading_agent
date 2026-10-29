#!/usr/bin/env python
# -*- coding: utf-8 -*-/
# @Time : 2025/4/12 17:20
# @Author : Jason
# @Email : Jasonforjob@qq.com
import json

from lib.dify.dify_client import DifyConfig, DifyAPIError
from lib.dify.workflow import WorkflowDifyClient, WorkflowRequest

entity_matrix=[
        {
            "entity": "food",
            "entity_type": "场景",
            "entity_count": 112
        },
        {
            "entity": "warming",
            "entity_type": "功能属性",
            "entity_count": 101
        },
        {
            "entity": "mat",
            "entity_type": "品名",
            "entity_count": 70
        },
        {
            "entity": "tray",
            "entity_type": "品名",
            "entity_count": 67
        },
        {
            "entity": "heating",
            "entity_type": "功能属性",
            "entity_count": 67
        },
        {
            "entity": "electric",
            "entity_type": "功能属性",
            "entity_count": 45
        },
        {
            "entity": "warmer",
            "entity_type": "功能属性",
            "entity_count": 42
        },
        {
            "entity": "silicone",
            "entity_type": "材质属性",
            "entity_count": 29
        },
        {
            "entity": "pad",
            "entity_type": "品名",
            "entity_count": 20
        },
        {
            "entity": "warm",
            "entity_type": "风格属性",
            "entity_count": 18
        },
        {
            "entity": "portable",
            "entity_type": "场景",
            "entity_count": 16
        },
        {
            "entity": "roll",
            "entity_type": "数量/套装",
            "entity_count": 15
        },
        {
            "entity": "plate",
            "entity_type": "品名",
            "entity_count": 13
        },
        {
            "entity": "hot",
            "entity_type": "风格属性",
            "entity_count": 13
        },
        {
            "entity": "trays",
            "entity_type": "品名",
            "entity_count": 12
        },
        {
            "entity": "keep",
            "entity_type": "功能属性",
            "entity_count": 11
        },
        {
            "entity": "plates",
            "entity_type": "品名",
            "entity_count": 9
        },
        {
            "entity": "adjustable",
            "entity_type": "功能属性",
            "entity_count": 9
        },
        {
            "entity": "countertop",
            "entity_type": "场景",
            "entity_count": 9
        },
        {
            "entity": "laudlife",
            "entity_type": "品牌",
            "entity_count": 8
        },
        {
            "entity": "kitchen",
            "entity_type": "场景",
            "entity_count": 8
        },
        {
            "entity": "travel",
            "entity_type": "场景",
            "entity_count": 8
        },
        {
            "entity": "heat",
            "entity_type": "场景",
            "entity_count": 8
        },
        {
            "entity": "pads",
            "entity_type": "品名",
            "entity_count": 6
        },
        {
            "entity": "party",
            "entity_type": "场景",
            "entity_count": 6
        },
        {
            "entity": "mats",
            "entity_type": "品名",
            "entity_count": 5
        },
        {
            "entity": "buffet",
            "entity_type": "品名",
            "entity_count": 5
        },
        {
            "entity": "temp",
            "entity_type": "品名",
            "entity_count": 5
        },
        {
            "entity": "table",
            "entity_type": "品名",
            "entity_count": 5
        },
        {
            "entity": "foldable",
            "entity_type": "功能属性",
            "entity_count": 5
        },
        {
            "entity": "temperature",
            "entity_type": "功能属性",
            "entity_count": 5
        },
        {
            "entity": "tempmaster",
            "entity_type": "品牌",
            "entity_count": 4
        },
        {
            "entity": "warmit",
            "entity_type": "品牌",
            "entity_count": 4
        },
        {
            "entity": "feet",
            "entity_type": "品名",
            "entity_count": 4
        },
        {
            "entity": "heated",
            "entity_type": "功能属性",
            "entity_count": 4
        },
        {
            "entity": "auto",
            "entity_type": "场景",
            "entity_count": 4
        },
        {
            "entity": "large",
            "entity_type": "特征属性",
            "entity_count": 3
        },
        {
            "entity": "master",
            "entity_type": "品牌",
            "entity_count": 3
        },
        {
            "entity": "miller",
            "entity_type": "品牌",
            "entity_count": 3
        },
        {
            "entity": "flora",
            "entity_type": "品牌",
            "entity_count": 3
        },
        {
            "entity": "connect",
            "entity_type": "品牌",
            "entity_count": 3
        },
        {
            "entity": "surface",
            "entity_type": "品牌",
            "entity_count": 3
        },
        {
            "entity": "market",
            "entity_type": "品名",
            "entity_count": 3
        },
        {
            "entity": "pot",
            "entity_type": "品名",
            "entity_count": 3
        },
        {
            "entity": "function",
            "entity_type": "品名",
            "entity_count": 3
        },
        {
            "entity": "extra",
            "entity_type": "功能属性",
            "entity_count": 3
        },
        {
            "entity": "smart",
            "entity_type": "功能属性",
            "entity_count": 3
        },
        {
            "entity": "rollup",
            "entity_type": "功能属性",
            "entity_count": 3
        },
        {
            "entity": "fast",
            "entity_type": "功能属性",
            "entity_count": 3
        },
        {
            "entity": "easy",
            "entity_type": "功能属性",
            "entity_count": 3
        },
        {
            "entity": "shut-off",
            "entity_type": "功能属性",
            "entity_count": 3
        },
        {
            "entity": "magic",
            "entity_type": "风格属性",
            "entity_count": 3
        },
        {
            "entity": "design",
            "entity_type": "风格属性",
            "entity_count": 3
        },
        {
            "entity": "outdoor",
            "entity_type": "场景",
            "entity_count": 3
        },
        {
            "entity": "matt",
            "entity_type": "材质属性",
            "entity_count": 3
        },
        {
            "entity": "family",
            "entity_type": "用户人群/人群特征",
            "entity_count": 2
        },
        {
            "entity": "raised",
            "entity_type": "特征属性",
            "entity_count": 2
        },
        {
            "entity": "dual",
            "entity_type": "特征属性",
            "entity_count": 2
        },
        {
            "entity": "feppo",
            "entity_type": "品牌",
            "entity_count": 2
        },
        {
            "entity": "wanish",
            "entity_type": "品牌",
            "entity_count": 2
        },
        {
            "entity": "amazon",
            "entity_type": "品牌",
            "entity_count": 2
        },
        {
            "entity": "precise",
            "entity_type": "品牌",
            "entity_count": 2
        },
        {
            "entity": "power",
            "entity_type": "品牌",
            "entity_count": 2
        },
        {
            "entity": "ntc",
            "entity_type": "品牌",
            "entity_count": 2
        },
        {
            "entity": "board",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "mill",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "warmers",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "dish",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "protects",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "settings",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "timer",
            "entity_type": "品名",
            "entity_count": 2
        },
        {
            "entity": "control",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "flameless",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "rapid",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "clean",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "protection",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "waterproof",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "oil-proof",
            "entity_type": "功能属性",
            "entity_count": 2
        },
        {
            "entity": "parties",
            "entity_type": "场景",
            "entity_count": 2
        },
        {
            "entity": "buffets",
            "entity_type": "场景",
            "entity_count": 2
        },
        {
            "entity": "dinner",
            "entity_type": "场景",
            "entity_count": 2
        },
        {
            "entity": "gatherings",
            "entity_type": "场景",
            "entity_count": 2
        },
        {
            "entity": "events",
            "entity_type": "场景",
            "entity_count": 2
        },
        {
            "entity": "pro",
            "entity_type": "产品型号",
            "entity_count": 2
        },
        {
            "entity": "2.0",
            "entity_type": "产品型号",
            "entity_count": 2
        },
        {
            "entity": "10s",
            "entity_type": "产品型号",
            "entity_count": 2
        },
        {
            "entity": "edge",
            "entity_type": "产品型号",
            "entity_count": 2
        },
        {
            "entity": "silicon",
            "entity_type": "材质属性",
            "entity_count": 2
        }
    ]

product_info={
    "product_name": "Warming Mat",
    "category": "Commercial Food Warmers",
    "brand": "YCDYCD",
    "differentiating_features": ["9-Level Temperature"]
}

async def main():
    config = DifyConfig(
        api_key="app-7o6CbN7gRVeJlGIhnYlBmLZd",
        base_url="http://www.dify.aiautoex.com/v1"
    )

    async with WorkflowDifyClient(config) as client:
        print(await client.get_app_info())

        # 流式执行
        request_streaming = WorkflowRequest(
            inputs={"entity_matrix": json.dumps(entity_matrix), "product_info": json.dumps(product_info)},
            response_mode='streaming',
            user='test'
        )
        try:
            async with client.execute_streaming_workflow(request_streaming) as stream:
                async for result in stream:
                    print(f"Streaming result: {result}")
        except DifyAPIError as e:
            print(f"Workflow failed: {e.code} - {e}")

        # # 阻塞执行
        # request_blocking = WorkflowRequest(
        #     inputs={"entity_matrix": json.dumps(entity_matrix), "product_info": json.dumps(product_info)},
        #     response_mode='blocking',
        #     user='test'
        # )
        # result = await client.execute_blocking_workflow(request_blocking)
        # print(result)

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())