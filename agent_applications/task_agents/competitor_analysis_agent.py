#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
竞品分析Agent
判断两个产品是否是竞品关系
"""
import json
import re
from typing import Any, Dict, Optional
from uuid import uuid4
from loguru import logger

from core.agent_base.task_base_agent import TaskBaseAgent
from core.models.agent_models import AgentStatus
from core.agent_mixin.task_agent_mixin import TaskAgentMixin
from core.agent_mixin.thinking_mode_mixin import ThinkingModeMixin
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_models import LLMModels


class CompetitorAnalysisAgent(
    TaskAgentMixin,
    ThinkingModeMixin,
    TaskBaseAgent
):
    """
    竞品分析Agent - 判断两个产品是否是竞品关系
    """

    AGENT_TYPE = "competitor_analysis"
    DEFAULT_CAPABILITIES = ["competitor_analysis", "product_comparison", "market_analysis"]
    
    # ==================== LLM 配置 ====================
    LLM_CONFIG = {
        "model_name": LLMModels.GPT_52,
        "temperature": 0.3,      # 更低的温度，更确定的分析结果
        "max_completion_tokens": 4096,
        "api_key_env": LLMModels.OPENAI_API_KEY_ENV
    }

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "竞品分析Agent",
        **kwargs
    ):
        """
        初始化竞品分析Agent

        Args:
            agent_id: Agent ID
            agent_name: Agent名称
            **kwargs: 其他参数
        """
        agent_id = agent_id or str(uuid4())
        
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=self.DEFAULT_CAPABILITIES,
            max_concurrent_tasks=kwargs.get("max_concurrent_tasks", 10),
            metadata=kwargs.get("metadata", {})
        )
        
        # LLM 实例将在 initialize() 中创建
        # 构建系统 Prompt
        self.system_prompt = self._build_system_prompt()
        
        # 注意：思维链组件将在initialize()中初始化，因为需要先创建LLM实例

    def _build_system_prompt(self) -> str:
        """构建系统 Prompt（兼容方法）"""
        return self._get_system_prompt()

    async def initialize(self) -> bool:
        """初始化Agent"""
        try:
            # 确保LLM已初始化（使用BaseAgent的_get_llm方法）
            if not self._get_llm():
                logger.error("竞品分析Agent创建LLM实例失败")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            # 初始化思维链组件（需要在LLM创建后）
            if self.llm:
                self._init_thinking_components(llm=self.llm, tools={}, system_prompt=self.system_prompt)
                
                # 更新系统 Prompt（确保是最新的）
                self.system_prompt = self._build_system_prompt()
                if hasattr(self, '_update_thinking_system_prompt'):
                    self._update_thinking_system_prompt(self.system_prompt)
            
            logger.info(f"竞品分析Agent初始化成功: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"竞品分析Agent初始化失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            return False

    async def cleanup(self) -> bool:
        """清理资源"""
        try:
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"竞品分析Agent清理失败: {e}")
            return False

    # ==================== TaskAgentMixin 实现 ====================
    
    def _validate_task(self, task: Dict[str, Any]) -> bool:
        """验证任务格式"""
        product1 = task.get("product1", {})
        product2 = task.get("product2", {})
        
        if not product1 or not product2:
            logger.warning("任务格式验证失败：缺少 product1 或 product2")
            return False
        
        product1_title = product1.get("title", "")
        product2_title = product2.get("title", "")
        
        if not product1_title or not product2_title:
            logger.warning("任务格式验证失败：产品标题不能为空")
            return False
        
        return True
    
    def _extract_task_params(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """提取任务参数"""
        product1 = task.get("product1", {})
        product2 = task.get("product2", {})
        
        return {
            "product1_title": product1.get("title", ""),
            "product1_description": product1.get("description", ""),
            "product2_title": product2.get("title", ""),
            "product2_description": product2.get("description", ""),
            "task_id": task.get("task_id") or str(uuid4()),
            "thinking_mode": task.get("thinking_mode", "normal")
        }
    
    async def _execute_normal_mode(
        self, 
        params: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行普通模式业务逻辑"""
        # 构建用户消息
        user_message = self._build_user_input_prompt(params, context)
        
        # 使用标准化的消息构建方式（系统提示词 + 用户消息）
        messages = self._build_messages(
            user_message=user_message,
            include_system_prompt=True
        )
        
        # 调用LLM（使用消息格式）
        llm_response = await self._call_llm_with_messages(messages)
        
        # 解析结果
        return self._parse_llm_response(llm_response, params, context)
    
    # 注意：_execute_cot_mode() 已由 TaskAgentMixin 提供默认实现，无需重复实现
    
    # 注意：_format_task_result() 已由 TaskAgentMixin 提供默认实现，无需重复实现
    
    # ==================== Prompt 实现 ====================
    
    def _get_system_prompt(self) -> str:
        """获取基础系统 Prompt"""
        return """你是一个亚马逊产品竞品分析专家，专门判断两个产品是否是竞品关系。

请从以下维度进行深入分析：
1. **产品类型**：首先判断产品类型（完整产品、配件、替换件、补充品等）
2. **目标市场**：是否面向相同的用户群体、市场细分
3. **核心功能**：主要功能是否重叠、相似或互补
4. **产品定位**：市场定位、价值主张是否相同或相似
5. **使用场景**：应用场景、解决的需求是否一致
6. **商业模式**：盈利模式、运营方式是否相似
7. **产品关系**：是直接竞争关系还是互补关系（如完整产品与配件）

判断标准：
- **竞品关系（is_competitor=true）**：两个产品在目标市场、核心功能、产品定位中有**两个或以上维度高度相似**，且是**直接竞争关系**（都是完整产品，可以互相替代）
- **非竞品关系（is_competitor=false）**：以下情况不应视为竞品：
  - 一个是完整产品，另一个是配件/替换件/补充品（它们是互补关系，不是竞争关系）
  - 只是功能相似但目标市场完全不同（如企业软件 vs 个人软件）
  - 定位相同但功能差异很大
  - 产品类型不同（如主机 vs 配件、软件 vs 硬件）

similarity_analysis_result判断标准（重要）：
**关键原则：从产品本身的角度判断，而不是从功能重叠的角度判断。即使两个产品有部分功能重叠（如都有加热功能），但如果产品类别不同、核心用途不同、解决的需求不同，应该是不相关。**

- **强相关**：两个产品都是完整产品，在目标市场、核心功能、产品定位中都高度相似，存在直接竞争关系，可以互相替代。例如：两个不同品牌的完整剃须刀、两个不同品牌的完整手机。

- **低相关**：产品之间存在明确的关联性，但关联度较低，无法互相替代。以下情况应判断为"低相关"：
  1. **产品与配件关系**：一个是完整产品，另一个是配件/替换件/补充品（如完整剃须刀 vs 替换刀头、完整手机 vs 手机壳）
  2. **明确的互补关系**：产品之间存在明确的互补关系，通常需要配合使用（如打印机 vs 墨盒、咖啡机 vs 咖啡豆）
  3. **功能相似但定位不同**：核心功能相似或属于同一产品类别，但市场定位、目标用户、价格区间有明显差异。例如：
     - 手动刮胡刀 vs 电动剃须刀（都是剃须工具，但使用方式、定位不同）
     - 入门级产品 vs 高端产品（功能相似，但定位不同）
     - 企业软件 vs 个人软件（功能相似，但目标用户不同）
  4. **同类型产品但用途不同**：属于同一产品类别或产品线，但具体用途、应用场景有明显差异。例如：
     - 同一品牌的手机 vs 平板电脑（都是智能设备，但用途不同）
     - 洗发水 vs 护发素（都是护发产品，但用途不同）
     - 不同型号的同一产品线（如iPhone 14 vs iPhone 15，功能相似但版本不同）

- **不相关**：产品之间**没有实质性关联性**，即使在某些表面维度上有微弱联系或部分功能重叠，但如果产品类别不同、核心用途不同、解决的需求完全不同、无法互相替代且不是互补关系，应判断为"不相关"。以下情况应判断为"不相关"：
  1. **产品类别不同**：即使都属于同一大类（如个人护理产品），但如果产品类别不同（如热疗产品 vs 美容产品、清洁产品 vs 护理产品），应判断为"不相关"。例如：
     - 加热垫（热疗产品，核心用途：缓解肌肉酸痛、保暖）vs 美容按摩仪（美容产品，核心用途：面部颈部护理、皮肤塑形）→ **不相关**（产品类别不同，核心用途不同，解决的需求不同）
     - 香薰机（环境改善产品）vs 耳塞（听力保护产品）→ **不相关**（产品类别不同）
     - 洗发水（清洁产品）vs 剃须刀（剃须工具）→ **不相关**（产品类别不同）
  2. **核心用途完全不同**：即使有部分功能重叠（如都有加热功能），但如果核心用途完全不同、解决的需求完全不同，应判断为"不相关"。例如：
     - 加热垫（核心用途：缓解肌肉酸痛、保暖）vs 美容按摩仪（核心用途：美容护肤、皮肤塑形）→ **不相关**（虽然都有加热功能，但核心用途完全不同）
  3. **产品类型完全不同**：如玩具 vs 个人护理产品、食品 vs 电子产品、服装 vs 工具等
  4. **目标市场完全不同**：如儿童产品 vs 成人产品、男性产品 vs 女性产品（且产品类型也不同）
  5. **使用场景完全不同**：如娱乐产品 vs 实用工具、装饰品 vs 功能性产品
  6. **所有维度都完全不同**：产品类型、目标市场、核心功能、产品定位、使用场景、商业模式等所有维度都完全不同

**判断"不相关"的关键标准**：
- **从产品本身的角度判断**：首先看产品类别和核心用途，而不是看功能重叠。如果产品类别不同、核心用途不同、解决的需求不同，即使有部分功能重叠（如都有加热功能），也应该是不相关。
- **产品类别不同**：即使都属于同一大类（如个人护理产品），但如果产品类别不同（如热疗产品 vs 美容产品），应判断为"不相关"
- **核心用途完全不同**：如果两个产品的核心用途完全不同、解决的需求完全不同，应判断为"不相关"
- **无法互相替代且不是互补关系**：如果两个产品无法互相替代，也不是必须配合使用的互补关系，应判断为"不相关"


**特别注意**：
- **关键：从产品本身的角度判断，而不是从功能重叠的角度判断。**
- 如果一个是完整产品，另一个是配件/替换件，即使功能相关，也应该判断为"低相关"，而不是"强相关"，因为它们不是直接竞争关系，而是互补关系。
- 对于完全无关的产品（如儿童玩具 vs 剃须刀、食品 vs 电子产品、香薰机 vs 耳塞），必须判断为"不相关"，而不是"低相关"。
- **不要仅仅因为都属于同一大类（如个人护理产品）就判断为"低相关"，必须看核心功能和解决的需求是否相同或相似。**

请以JSON格式返回分析结果，格式如下：
{
    "is_competitor": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "详细的分析理由，说明为什么是或不是竞品，包括各维度的分析",
    "similarity_analysis": {
        "target_market": "高/中/低",
        "functionality": "高/中/低",
        "positioning": "高/中/低"
    },
    "similarity_analysis_result": "强相关/低相关/不相关"
}

只返回JSON，不要返回其他内容。"""

    # ==================== 业务逻辑方法 ====================
    
    def _build_user_input_prompt(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建用户输入 Prompt（统一接口）

        Args:
            params: 任务参数
            context: 上下文信息

        Returns:
            用户输入 Prompt 字符串
        """
        product1_title = params.get("product1_title", "")
        product1_description = params.get("product1_description", "")
        product2_title = params.get("product2_title", "")
        product2_description = params.get("product2_description", "")
        
        prompt = f"""请分析以下两个产品是否是竞品关系。

产品A：
标题：{product1_title}
描述：{product1_description or '无描述'}

产品B：
标题：{product2_title}
描述：{product2_description or '无描述'}"""
        
        return prompt

    def _parse_llm_response(
        self,
        llm_response: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        解析LLM返回的分析结果（统一接口）

        Args:
            llm_response: LLM返回的文本
            params: 任务参数
            context: 上下文信息

        Returns:
            解析后的结果字典
        """
        try:
            # 检查响应是否为空
            if not llm_response or not llm_response.strip():
                logger.warning("LLM响应为空，返回默认结果")
                raise json.JSONDecodeError("Empty response", llm_response, 0)
            
            # 尝试提取JSON（支持多种格式）
            result = None
            
            # 方法1: 尝试直接解析整个响应
            try:
                result = json.loads(llm_response.strip())
            except json.JSONDecodeError:
                pass
            
            # 方法2: 使用正则表达式提取JSON对象（支持嵌套）
            if result is None:
                # 尝试匹配最外层的JSON对象
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
            
            # 方法3: 尝试提取代码块中的JSON
            if result is None:
                code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
                if code_block_match:
                    try:
                        result = json.loads(code_block_match.group(1))
                    except json.JSONDecodeError:
                        pass
            
            # 如果所有方法都失败，抛出异常
            if result is None:
                raise json.JSONDecodeError("No valid JSON found", llm_response, 0)
            
            # 验证和规范化结果
            similarity_analysis_result = result.get("similarity_analysis_result", "")
            
            # 验证similarity_analysis_result的有效值
            valid_results = ["强相关", "低相关", "不相关"]
            if similarity_analysis_result not in valid_results:
                logger.warning(
                    f"无效的similarity_analysis_result值: {similarity_analysis_result}，"
                    f"有效值: {valid_results}，将使用默认值"
                )
                similarity_analysis_result = None  # 默认值

            parsed_result = {
                "is_competitor": bool(result.get("is_competitor", False)),
                "confidence": float(result.get("confidence", 0.5)),
                "reasoning": str(result.get("reasoning", "无分析理由")),
                "similarity_analysis": result.get("similarity_analysis", {
                    "target_market": "未知",
                    "functionality": "未知",
                    "positioning": "未知"
                }),
                "similarity_analysis_result": similarity_analysis_result
            }
            
            # 确保置信度在0-1之间
            parsed_result["confidence"] = max(0.0, min(1.0, parsed_result["confidence"]))
            
            return parsed_result
            
        except json.JSONDecodeError as e:
            # 记录更详细的错误信息
            response_preview = llm_response[:500] if llm_response else "空响应"
            logger.warning(
                f"解析LLM响应失败: {e}, "
                f"响应长度: {len(llm_response) if llm_response else 0}, "
                f"响应预览: {response_preview}"
            )
            # 返回默认结果，similarity_analysis_result 为 None 表示未知/失败
            return {
                "is_competitor": None,
                "confidence": 0.0,
                "reasoning": f"解析失败: {str(e)}。原始响应: {response_preview[:200]}",
                "similarity_analysis": {
                    "target_market": "未知",
                    "functionality": "未知",
                    "positioning": "未知"
                },
                "similarity_analysis_result": None  # None 表示分析失败，入库为 Not Available
            }
        except Exception as e:
            logger.error(f"解析分析结果时发生错误: {e}", exc_info=True)
            return {
                "is_competitor": None,
                "confidence": 0.0,
                "reasoning": f"处理失败: {str(e)}",
                "similarity_analysis": {
                    "target_market": "未知",
                    "functionality": "未知",
                    "positioning": "未知"
                },
                "similarity_analysis_result": None  # None 表示分析失败，入库为 Not Available
            }

    # 注意：LLM 调用方法已集成到 BaseAgent 中（_call_llm, _call_llm_with_messages）
    # 消息构建方法已集成到 BaseAgent 中（_build_messages）

