import json
import hmac
import base64
import datetime
from typing import Dict, Optional, List

import httpx

from lib.okx.utils import retry_async, NonRetryableRequestError


class OkxBase:
    def __init__(self, API_KEY, SECRET_KEY, PASSPHRASE, IS_SANDBOX=False, proxy=None):
        self.api_key = API_KEY
        self.secret_key = SECRET_KEY
        self.passphrase = PASSPHRASE
        self.max_retries = 3
        self.proxy = proxy
        self.is_sandbox = IS_SANDBOX

        # OKX 模拟盘 REST 仍然走正式 API 域名与路径，靠请求头切换环境。
        self.base_url = "https://www.okx.com/api/v5"

        self.root_url = "/api/v5"

    def _get_timestamp(self):
        now = datetime.datetime.utcnow()
        return now.isoformat("T", "milliseconds") + "Z"

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """生成OKX API签名
        
        Args:
            timestamp: 时间戳
            method: HTTP方法
            request_path: 请求路径（包含查询参数）
            body: 请求体内容

        Returns:
            str: Base64编码的签名
        """
        # 构建签名字符串：timestamp + method + request_path + body
        message = timestamp + method + request_path + body

        # 使用HMAC-SHA256生成签名
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        d = mac.digest()
        return base64.b64encode(d).decode()

    @retry_async(max_retries=3)
    async def _request(self, method: str, path: str, params: Optional[Dict] = None,
                       data: Optional[Dict] = None) -> Dict:
        """发送HTTP请求到OKX API
        
        Args:
            method: HTTP方法，如 "GET" 或 "POST"
            path: API路径，如 "/market/ticker"
            params: URL查询参数
            data: 请求体数据
            
        Returns:
            Dict: API响应
        """
        timestamp = self._get_timestamp()

        # 构建请求路径（requestPath）
        # 根据官方文档：GET请求参数是requestPath的一部分，不是body
        request_path = path
        query_string = ""
        if params and method == "GET":
            # 对于GET请求，将查询参数按字母顺序排序并添加到路径中
            # 确保参数顺序与签名时一致
            sorted_params = sorted(params.items())
            query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
            if query_string:
                request_path = f"{path}?{query_string}"

        # 构建请求体字符串（body）
        # 根据官方文档：只有POST请求才有body，GET请求的body为空
        body = ""
        if data and method == "POST":
            # 使用标准JSON格式
            body = json.dumps(data, separators=(',', ':'))

        # 生成签名：timestamp + method + requestPath + body
        # requestPath 应该包含完整的路径，包括 /api/v5 前缀
        full_request_path = self.root_url + request_path
        signature = self._sign(timestamp, method, full_request_path, body)

        # 构建请求头
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "OKX-API-Client/1.0.0"
        }

        if self.is_sandbox:
            headers["x-simulated-trading"] = "1"

        # 构建完整URL
        # 对于GET请求，必须使用构建好的查询字符串，确保与签名一致
        if method == "GET" and query_string:
            url = f"{self.base_url}{path}?{query_string}"
        else:
            url = f"{self.base_url}{path}"

        # 打印请求信息，便于调试
        print(f"请求URL: {url}")
        print(f"请求方法: {method}")
        print(f"请求路径: {request_path}")
        print(f"请求参数: {params}")
        print(f"查询字符串: {query_string}")
        print(f"请求体: {body}")
        # print(f"签名字符串: {timestamp + method + self.root_url + request_path + body}")
        # print(f"签名: {signature}")

        # 设置httpx客户端选项
        client_kwargs = {
            "verify": False,  # 禁用SSL验证
            "timeout": 60.0  # 设置超时时间
        }

        if self.proxy:
            client_kwargs["proxies"] = {"all://": self.proxy}

        # 发送请求
        async with httpx.AsyncClient(**client_kwargs) as client:
            if method == "GET":
                # 对于GET请求，直接使用构建好的URL（包含查询字符串），不再传递params
                # 这样可以确保请求URL与签名时使用的路径完全一致
                if query_string:
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")

            # 使用_parse_response方法处理响应
            return await self._parse_response(response)

    async def _parse_response(self, response):
        """解析API响应，处理不同的错误码
        
        Args:
            response: HTTP响应对象
            
        Returns:
            Dict: 解析后的响应数据
            
        Raises:
            Exception: 如果响应包含错误
        """
        # 解析JSON响应（无论HTTP状态码是什么，都先尝试解析）
        try:
            result = response.json()
        except Exception as e:
            # 如果无法解析JSON，直接抛出HTTP错误
            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}, 响应内容: {response.text}")
            raise Exception(f"解析JSON响应失败: {str(e)}, 响应内容: {response.text}")

        # 检查HTTP状态码
        if response.status_code != 200:
            # HTTP状态码不是200，尝试从JSON响应中提取错误信息
            error_msg = result.get("msg", "未知错误")
            error_code = result.get("code", "未知")
            raise NonRetryableRequestError(
                f"HTTP错误: {response.status_code}, API错误码: {error_code}, 错误信息: {error_msg}"
            )

        # 获取错误码
        code = result.get("code")

        # 处理不同的错误码
        if code == "0":
            # 成功
            return result
        elif code == "1":
            # 操作全部失败
            raise NonRetryableRequestError(f"操作全部失败: {self._build_error_message(result)}")
        elif code == "2":
            # 批量操作部分成功
            print(f"警告: 批量操作部分成功: {result.get('msg', '未知错误')}")
            return result
        elif code and isinstance(code, str) and code.isdigit() and 50000 <= int(code) <= 59999:
            # REST API 错误
            error_msg = result.get("msg", "未知错误")
            if 50000 <= int(code) <= 53999:
                # 公共错误
                raise NonRetryableRequestError(f"公共错误 ({code}): {error_msg}")
            else:
                # 其他REST API错误
                raise NonRetryableRequestError(f"REST API错误 ({code}): {error_msg}")
        else:
            # 其他未知错误
            raise NonRetryableRequestError(f"API错误 ({code}): {self._build_error_message(result)}")

    def _build_error_message(self, result: Dict) -> str:
        messages: List[str] = []

        top_level_msg = str(result.get("msg") or "").strip()
        if top_level_msg:
            messages.append(top_level_msg)

        data = result.get("data")
        if isinstance(data, list):
            for index, item in enumerate(data):
                if not isinstance(item, dict):
                    continue

                sub_code = str(item.get("sCode") or "").strip()
                sub_msg = str(item.get("sMsg") or "").strip()
                if not sub_code and not sub_msg:
                    continue

                detail = sub_msg or "未知子错误"
                if sub_code and sub_code != "0":
                    detail = f"[{sub_code}] {detail}"
                if len(data) > 1:
                    detail = f"第{index + 1}项: {detail}"
                messages.append(detail)

        deduplicated = list(dict.fromkeys(msg for msg in messages if msg))
        return " | ".join(deduplicated) if deduplicated else "未知错误"
