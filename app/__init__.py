#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:13
# @Author : Jason
# @Email : Jasonforjob@qq.com

from fastapi import FastAPI

from app.public.factory import AppFactory


def create_app(env="prod") -> FastAPI:
    """应用工厂入口"""
    return (
        AppFactory(env).build()
    )