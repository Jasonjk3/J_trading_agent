#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/8 17:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
from contextlib import asynccontextmanager
# dify_client/agent.py
from typing import Optional, AsyncGenerator, List, Union, Dict, Any
from pydantic import BaseModel, Field, validator
import httpx
from .dify_client import BaseDifyClient,DifyConfig, DifyAPIError




class AgentDifyClient(BaseDifyClient):
    def __init__(self, config: DifyConfig):
        super().__init__(config)



