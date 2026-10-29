#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/7 10:11
# @Author : Jason
# @Email : Jasonforjob@qq.com
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

import platform
import base64

from dotenv import load_dotenv, find_dotenv
from pydantic import Field
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class BaseConfig(BaseSettings):
    ENVIRONMENT: str = Field(default="dev", env="ENVIRONMENT")

    SERVER_HOST: str = Field(default="127.0.0.1", env="SERVER_HOST")

    SERVER_PORT: int = Field(default=8005, env="SERVER_PORT")

    SECRET_KEY: str = Field(env="SECRET_KEY")

    VERSION: str = Field(default="0.0.1", env="VERSION")

    ACCESS_TOKEN_EXPIRE_DAY: int = Field(default=5, env="ACCESS_TOKEN_EXPIRE_DAY")

    MYSQL_HOST: str = Field(default="127.0.0.1", env="MYSQL_HOST")
    MYSQL_USERNAME: str = Field(default="xxxx", env="MYSQL_USERNAME")
    MYSQL_PORT: int = Field(default=3306, env="MYSQL_PORT")
    MYSQL_PASSWORD: str = Field(default="xxxx", env="MYSQL_PASSWORD")
    MYSQL_DB: str = Field(default="xxxx", env="MYSQL_DB")
    
    LLM_PROXY: Optional[str] = Field(default=None, env="LLM_PROXY")

    class Config:
        load_dotenv(find_dotenv(".env", True), override=True)

    @property
    def PAYONNER_AUTHORIZATION(self) -> str:
        return f"Basic {base64.b64encode(f'{self.PAYONNER_CLIENT_ID}:{self.PAYONNER_CLIENT_SECRET}'.encode()).decode()}"


class Settings:

    PRIVATE_KEY = None

    # 无需鉴权的
    ANONYMOUS_PATH_LIST = [
        "POST/svip/Login",
        "GET/svip/GetCaptcha",
        "GET/svip/GetBookCaptcha",
        "GET/",
    ]

    SPE_ANONYMOUS_PATH_LIST = [
        "GET/svip/user/info",
        "PUT/svip/user/create",
        "PUT/svip/user/update",
        "PUT/svip/user/delete",
    ]

    def __init__(self):
        self.app_config = BaseConfig()

        # 使用 quote_plus 确保特殊字符被正确编码
        self.DATABASE_URL = self.construct_mysql_url(
            self.app_config.MYSQL_USERNAME,
            self.app_config.MYSQL_PASSWORD,
            self.app_config.MYSQL_HOST,
            self.app_config.MYSQL_PORT,
            self.app_config.MYSQL_DB
        )


    @staticmethod
    def construct_mysql_url(username, password, host, port, database):
        return f"mysql+mysqlconnector://{quote_plus(username)}:" \
               f"{quote_plus(password)}@{host}:{port}/{database}"

    @staticmethod
    def construct_redis_url(password, host, port, db):
        password = f":{quote_plus(password)}@" if password else ""
        return f"redis://{password}{host}:{port}/{db}"

    @staticmethod
    def read_private_key_from_file(file_path):

        if platform.system() == 'Windows':
            file_path = file_path.replace('\\', '/')
        else:
            file_path = file_path.replace('\\', '/')

        try:
            with open(file_path, 'r') as file:
                return file.read()
        except FileNotFoundError:
            raise f"The private key file at {file_path} was not found."
        except Exception as e:
            raise f"An error occurred while reading the private key: {e}"


settings = Settings()
app_config = settings.app_config