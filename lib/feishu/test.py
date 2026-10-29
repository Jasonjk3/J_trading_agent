#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/8/27 16:45
# @Author : Jason
# @Email : Jasonforjob@qq.com
import time
from loguru import logger
from lib.feishu.base.feishu_public import LocaleType
from lib.feishu.feishu_sdk import FeishuSDK



app_id = os.environ["FEISHU_APP_ID"]
app_secret = os.environ["FEISHU_APP_SECRET"]
# 初始化SDK
sdk = FeishuSDK(app_id=app_id, app_secret=app_secret)

# 获取访问令牌
logger.info("正在获取访问令牌...")
token_result = sdk.get_app_access_token()
if token_result['state'] != 'success':
    logger.error(f"获取访问令牌失败: {token_result['msg']}")
    exit(1)

tenant_access_token = token_result['data']['tenant_access_token']
logger.info("访问令牌获取成功")

# 测试参数
approval_code = "96725FAA-D61C-4EE6-A21F-1E89CDF2C2EC"  # 示例审批定义Code

# 设置时间范围（最近7天）
end_time = int(time.time() * 1000)  # 当前时间戳（毫秒）
start_time = end_time - (7 * 24 * 60 * 60 * 1000)  # 7天前的时间戳（毫秒）

logger.info(f"开始测试获取所有审批实例...")
logger.info(f"审批定义Code: {approval_code}")
logger.info(f"时间范围: {start_time} - {end_time}")

# 测试获取所有审批实例ID
result = sdk.get_all_approval_instances(
    tenant_access_token=tenant_access_token,
    approval_code=approval_code,
    start_time=str(start_time),
    end_time=str(end_time),
    page_size=50
)

if result['state'] == 'success':
    data = result['data']
    all_instance_codes = data.get('instance_code_list', [])
    total_count = data.get('total_count', 0)

    logger.info(f"✅ 获取所有审批实例ID成功!")
    logger.info(f"总共获取到 {total_count} 个审批实例")

    if all_instance_codes:
        logger.info("前5个审批实例ID:")
        for i, instance_code in enumerate(all_instance_codes[:5]):
            logger.info(f"  {i + 1}. {instance_code}")

        if len(all_instance_codes) > 5:
            logger.info(f"  ... 还有 {len(all_instance_codes) - 5} 个实例")

        # 测试获取第一个实例的详细信息
        logger.info(f"\n正在获取第一个实例的详细信息...")
        first_instance = all_instance_codes[0]
        detail_result = sdk.get_approval_instance_detail(
            tenant_access_token=tenant_access_token,
            instance_id=first_instance,
            locale=LocaleType.ZH_CN
        )

        if detail_result['state'] == 'success':
            detail_data = detail_result['data']
            logger.info(f"✅ 获取实例详情成功!")
            logger.info(f"实例ID: {first_instance}")
            logger.info(f"审批名称: {detail_data.get('approval_name')}")
            logger.info(f"审批状态: {detail_data.get('status')}")
            logger.info(f"发起人: {detail_data.get('user_id')}")
            logger.info(f"创建时间: {detail_data.get('start_time')}")
            logger.info(f"审批单号: {detail_data.get('serial_number')}")

            # 显示任务列表
            task_list = detail_data.get('task_list', [])
            if task_list:
                logger.info(f"任务数量: {len(task_list)}")
                for task in task_list[:3]:  # 只显示前3个任务
                    logger.info(
                        f"  - 任务ID: {task.get('id')}, 状态: {task.get('status')}, 节点: {task.get('node_name')}")
        else:
            logger.error(f"❌ 获取实例详情失败: {detail_result['msg']}")
    else:
        logger.info("在指定时间范围内没有找到审批实例")
else:
    logger.error(f"❌ 获取所有审批实例ID失败: {result['msg']}")

logger.info("测试完成!")