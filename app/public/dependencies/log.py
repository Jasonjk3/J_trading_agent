#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/7 15:41
# @Author : Jason
# @Email : Jasonforjob@qq.com
import json
import os
import sys
import traceback
from datetime import datetime

import loguru
from loguru import logger


def custom_sink(message) -> None:
    record = message.record
    custom_record = {
        "level": record["level"].name,
        "msg": record["message"],
        **record["extra"],
        "file": record["file"].path,
        "line": record["line"],
        "process_name": record["process"].name,
        "process_id": record["process"].id,
        "datetime": str(record["time"]),
        "datetime_format": datetime.strptime(
            str(record["time"]), "%Y-%m-%d %H:%M:%S.%f%z"
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "time": record["time"].timestamp(),
        "exception": None,
    }
    if custom_record["level"] == "ERROR":
        custom_record["exception"] = traceback.format_exc()
    sys.stderr.write(json.dumps(custom_record, ensure_ascii=False) + "\n")


def initialize_logger(runtime_env, log_format, level="INFO"):
    logger.remove()
    if log_format == "json":
        logger.add(sink=custom_sink, level=level)
    else:
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                   "<level>{level: <8}</level> | "
                   "<Y><k>{process.name}-{process.id}</k></Y> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                   "<level>{message}</level>",
        )

    logger.info(f"当前运行环境: {runtime_env}, log format: {log_format}")

    if runtime_env != "pro":
        logger.info(f"当前运行环境: {runtime_env}, 接口文档地址: http://127.0.0.1:5005/docs")


def init_log():
    runtime_env = os.environ.get("ENVIRONMENT", "dev")
    if runtime_env == "pro":
        log_format_default = "json"
    else:
        log_format_default = "test"

    log_format = os.getenv("LOG_FORMAT", log_format_default)
    initialize_logger(runtime_env, log_format)