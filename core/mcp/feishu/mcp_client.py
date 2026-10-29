#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP 客户端基类
提供与 MCP 服务器通信的基础功能
"""
import json
import subprocess
import os
import threading
from typing import Optional, Dict, Any, List
from loguru import logger


class MCPClient:
    """MCP (Model Context Protocol) 客户端基类"""
    
    def __init__(
        self,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ):
        """
        初始化 MCP 客户端
        
        Args:
            command: MCP 服务器启动命令
            args: 命令参数列表
            env: 环境变量字典
            timeout: 请求超时时间（秒），默认 30 秒
        """
        self.command = command
        self.args = args
        self.env = env or {}
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._responses: Dict[int, Dict[str, Any]] = {}
        self._response_event = threading.Event()
    
    def start(self) -> None:
        """
        启动 MCP 服务器进程并初始化连接
        
        Raises:
            RuntimeError: 启动失败时抛出
        """
        if self.process is not None:
            logger.warning('MCP 服务器已经在运行')
            return
        
        try:
            # 合并环境变量
            env = os.environ.copy()
            env.update(self.env)
            
            # 启动进程
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )
            
            logger.info(f'MCP 服务器已启动: {self.command} {" ".join(self.args)}')
            
            # 启动响应监听线程
            self._start_response_listener()
            
            # 初始化 MCP 连接
            self._initialize()
            
        except Exception as e:
            logger.error(f'启动 MCP 服务器失败: {e}')
            if self.process:
                self.stop()
            raise RuntimeError(f'启动 MCP 服务器失败: {str(e)}')
    
    def _initialize(self) -> None:
        """初始化 MCP 连接"""
        try:
            # 发送初始化请求
            init_request = {
                'jsonrpc': '2.0',
                'method': 'initialize',
                'id': self._get_next_request_id(),
                'params': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {},
                    'clientInfo': {
                        'name': 'feishu-mcp-client',
                        'version': '1.0.0'
                    }
                }
            }
            
            request_json = json.dumps(init_request, ensure_ascii=False)
            if self.process and self.process.stdin:
                self.process.stdin.write(request_json + '\n')
                self.process.stdin.flush()
            
            # 等待初始化响应
            self._response_event.clear()
            if self._response_event.wait(timeout=self.timeout):
                with self._lock:
                    response = self._responses.pop(init_request['id'], None)
                
                if response and 'error' not in response:
                    logger.info('MCP 连接初始化成功')
                    # 发送 initialized 通知
                    self._send_notification('notifications/initialized', {})
                else:
                    logger.warning('MCP 初始化响应异常')
        except Exception as e:
            logger.warning(f'MCP 初始化失败: {e}，继续执行')
    
    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        发送通知（不需要响应）
        
        Args:
            method: 方法名
            params: 参数
        """
        if self.process is None or self.process.stdin is None:
            return
        
        notification = {
            'jsonrpc': '2.0',
            'method': method
        }
        
        if params:
            notification['params'] = params
        
        try:
            notification_json = json.dumps(notification, ensure_ascii=False)
            self.process.stdin.write(notification_json + '\n')
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f'发送通知失败: {e}')
    
    def _start_response_listener(self) -> None:
        """启动响应监听线程"""
        def listen():
            if self.process is None or self.process.stdout is None:
                return
            
            try:
                # MCP 协议使用 NDJSON 格式（每行一个 JSON 对象）
                for line in iter(self.process.stdout.readline, ''):
                    if not line or not line.strip():
                        continue
                    
                    line = line.strip()
                    try:
                        response = json.loads(line)
                        request_id = response.get('id')
                        
                        # 处理响应（有 id 的）或通知（无 id 的）
                        if request_id is not None:
                            with self._lock:
                                self._responses[request_id] = response
                            self._response_event.set()
                        else:
                            # 处理服务器通知
                            method = response.get('method')
                            if method:
                                logger.debug(f'收到 MCP 通知: {method}')
                    except json.JSONDecodeError as e:
                        logger.warning(f'解析响应失败: {e}, 内容: {line[:100]}')
                    except Exception as e:
                        logger.error(f'处理响应异常: {e}')
                        
            except Exception as e:
                logger.error(f'响应监听线程异常: {e}')
        
        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
    
    def _get_next_request_id(self) -> int:
        """获取下一个请求 ID"""
        with self._lock:
            self._request_id += 1
            return self._request_id
    
    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        调用 MCP 方法
        
        Args:
            method: 方法名
            params: 方法参数
            
        Returns:
            响应数据
            
        Raises:
            RuntimeError: 服务器未启动或调用失败时抛出
        """
        if self.process is None or self.process.stdin is None:
            raise RuntimeError('MCP 服务器未启动，请先调用 start() 方法')
        
        request_id = self._get_next_request_id()
        request = {
            'jsonrpc': '2.0',
            'method': method,
            'id': request_id
        }
        
        if params:
            request['params'] = params
        
        try:
            # 发送请求
            request_json = json.dumps(request, ensure_ascii=False)
            self.process.stdin.write(request_json + '\n')
            self.process.stdin.flush()
            
            logger.debug(f'发送 MCP 请求: {method}, id: {request_id}')
            
            # 等待响应
            self._response_event.clear()
            if not self._response_event.wait(timeout=self.timeout):
                raise RuntimeError(f'MCP 请求超时: {method}')
            
            # 获取响应
            with self._lock:
                response = self._responses.pop(request_id, None)
            
            if response is None:
                raise RuntimeError(f'未收到响应: {method}')
            
            # 检查错误
            if 'error' in response:
                error = response['error']
                raise RuntimeError(
                    f'MCP 调用失败: {error.get("message", "未知错误")}, '
                    f'code: {error.get("code", "未知")}'
                )
            
            return response.get('result', {})
            
        except Exception as e:
            logger.error(f'MCP 调用异常: {e}')
            raise
    
    def stop(self) -> None:
        """停止 MCP 服务器进程"""
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.error(f'停止 MCP 服务器失败: {e}')
            finally:
                self.process = None
                logger.info('MCP 服务器已停止')
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()

