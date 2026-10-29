#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/7 10:04
# @Author : Jason
# @Email : Jasonforjob@qq.com

# api/core/factory.py
from contextlib import asynccontextmanager
import importlib
import pkgutil
from pathlib import Path

from fastapi import Depends, FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core.infrastructure.database.async_database import AsyncDatabase
from app.public.dependencies.log import init_log
from app.public.middleware.auth import AuthMiddleware
from app.public.middleware.logging import LoggingMiddleware
from configs.config import app_config


class AppFactory:
    """应用工厂核心类"""

    def __init__(self, env: str = "dev"):
        self.env = env
        self._routers = []
        self._dependencies = {}
        self._config = app_config
        self._auto_discover_routers()

    def add_router(self, prefix: str, router):
        """注册路由"""
        self._routers.append((prefix, router))
        return self

    def _auto_discover_routers(self):
        """自动注册路由"""
        routers = self.auto_discover_routers()
        for router in routers:
            prefix = self._get_router_prefix(router)
            self.add_router(prefix, router)

    def _get_router_prefix(self, router: APIRouter) -> str:
        """从路由元数据获取前缀"""
        prefix = "/api/v1"
        if hasattr(router, "prefix"):
            return router.prefix
        return prefix

    def add_dependency(self, name: str, dependency):
        """注册全局依赖"""
        self._dependencies[name] = dependency
        return self

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """生命周期管理"""
        # 数据库已在 build() 中通过 _init_resources() 初始化并挂到 app.state.db。
        # 此处禁止再次 _init_resources()，否则 self.db 会指向新引擎，而 app.state.db
        # 仍是旧引擎，导致连接泄漏，且消息面等后台任务与请求侧可能不一致。
        from app.public.init_services import init_services, cleanup_services
        from core.infrastructure.database.schema_compatibility import (
            ensure_message_push_schema,
            ensure_data_monitor_schema,
            ensure_runtime_schema_compatibility,
        )

        await ensure_runtime_schema_compatibility(self.db.engine)
        await ensure_message_push_schema(self.db.engine)
        await ensure_data_monitor_schema(self.db.engine)
        await init_services(app)
        yield
        await cleanup_services(app)
        await self._release_resources()

    def _init_resources(self):
        """初始化数据库资源"""
        self.db = AsyncDatabase(self._config)

    async def _release_resources(self):
        """关闭数据库连接池"""
        await self.db.engine.dispose()

    def build(self) -> FastAPI:
        """构建FastAPI应用实例"""
        app = FastAPI(
            title="Sales Forecast API",
            lifespan=self._lifespan,
            dependencies=[Depends(self.get_global_dependencies)]
        )

        # 加载日志
        init_log()

        # 初始化数据库资源
        self._init_resources()

        # 加载中间件（注意：中间件顺序很重要，后添加的先执行）
        # app.add_middleware(AuthMiddleware)
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 允许所有来源，生产环境建议限制具体域名
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 加载路由
        for prefix, router in self._routers:
            app.include_router(router, prefix=prefix)
        
        # 加载V1版本路由
        from app.v1 import v1_router
        app.include_router(v1_router)

        # # 异常处理
        # self._register_exception_handlers(app)

        app.state.db = self.db  # 挂载到应用状态

        return app

    def get_global_dependencies(self):
        """生成全局依赖项"""
        return list(self._dependencies.values())

    def auto_discover_routers(self,
            package_path: str = "api/routers",
            router_name: str = "router"
    ) -> list:
        """自动发现路由模块"""
        package_dir = Path(package_path)
        modules = []

        # 遍历路由目录
        for finder, name, _ in pkgutil.iter_modules([str(package_dir)]):
            module = importlib.import_module(f"{package_path.replace('/', '.')}.{name}")
            if hasattr(module, router_name):
                router = getattr(module, router_name)
                modules.append(router)

        return modules
