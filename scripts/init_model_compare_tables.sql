-- ============================================================================
-- 模型对比模块 数据库初始化脚本 v2.0
-- 支持多服务商、直接传递 API Key 的架构
-- 作者：AI Assistant
-- 日期：2026-02-07
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. API 配置表 (model_compare_api_config)
-- 存储第三方 LLM 供应商的 API 配置
-- 支持 OpenAI 官方、各种中转服务商、私有部署等
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `model_compare_api_config` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name` VARCHAR(64) NOT NULL COMMENT '配置名称（如：OpenAI官方、XX中转等）',
    `provider` VARCHAR(32) NOT NULL COMMENT '供应商名称（显示用）',
    `api_type` VARCHAR(16) NOT NULL DEFAULT 'generic' COMMENT 'API 协议类型: openai / deepseek / generic',
    `api_key` VARCHAR(512) NOT NULL COMMENT 'API Key',
    `api_url` VARCHAR(256) DEFAULT NULL COMMENT 'API URL（完整地址，如 https://api.xxx.com/v1/chat/completions）',
    `extra_headers` JSON DEFAULT NULL COMMENT '额外请求头（JSON格式，某些服务商需要）',
    `extra_params` JSON DEFAULT NULL COMMENT '额外请求参数（JSON格式）',
    `description` VARCHAR(256) DEFAULT NULL COMMENT '配置描述',
    `is_default` TINYINT NOT NULL DEFAULT 0 COMMENT '是否默认配置',
    `is_active` TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    `user_id` VARCHAR(64) DEFAULT NULL COMMENT '用户ID（可选，支持多租户）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_name_user` (`name`, `user_id`),
    INDEX `idx_provider` (`provider`),
    INDEX `idx_api_type` (`api_type`),
    INDEX `idx_is_active` (`is_active`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API 配置表';


-- ----------------------------------------------------------------------------
-- 2. 模型管理表 (model_compare_model)
-- 存储可用模型配置，每个模型关联一个 API 配置
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `model_compare_model` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `model_id` VARCHAR(64) NOT NULL COMMENT '模型ID（如 gpt-4o, deepseek-chat）',
    `name` VARCHAR(64) NOT NULL COMMENT '模型显示名称',
    `provider` VARCHAR(32) NOT NULL COMMENT '提供商显示名称',
    `description` VARCHAR(512) DEFAULT NULL COMMENT '模型描述',
    `max_tokens` INT DEFAULT NULL COMMENT '模型上下文 Token 上限',
    `max_output_tokens` INT DEFAULT NULL COMMENT '单次请求最大输出 Token 数',
    `supports_streaming` TINYINT NOT NULL DEFAULT 1 COMMENT '是否支持流式输出',
    `supports_thinking` TINYINT NOT NULL DEFAULT 0 COMMENT '是否支持思考模式',
    `use_max_completion_tokens` TINYINT NOT NULL DEFAULT 0 COMMENT '是否使用 max_completion_tokens（o1/o3 等模型需要）',
    `input_price_per_1m` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '输入价格（$/1M tokens）',
    `output_price_per_1m` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '输出价格（$/1M tokens）',
    `api_config_id` INT DEFAULT NULL COMMENT '关联的 API 配置ID（必须先创建 API 配置）',
    `custom_params` JSON DEFAULT NULL COMMENT '模型特定参数（JSON格式）',
    `status` VARCHAR(16) NOT NULL DEFAULT 'unknown' COMMENT '可用状态: available / unavailable / unknown',
    `last_test_at` DATETIME DEFAULT NULL COMMENT '最后测试时间',
    `last_test_latency_ms` INT DEFAULT NULL COMMENT '最后测试延迟（毫秒）',
    `last_test_error` TEXT DEFAULT NULL COMMENT '最后测试错误信息',
    `is_active` TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序权重（越小越靠前）',
    `user_id` VARCHAR(64) DEFAULT NULL COMMENT '用户ID（可选）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_model_user` (`model_id`, `user_id`),
    INDEX `idx_model_id` (`model_id`),
    INDEX `idx_provider` (`provider`),
    INDEX `idx_api_config_id` (`api_config_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_is_active` (`is_active`),
    INDEX `idx_user_id` (`user_id`),
    CONSTRAINT `fk_model_api_config` FOREIGN KEY (`api_config_id`) 
        REFERENCES `model_compare_api_config` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型管理表';


-- ----------------------------------------------------------------------------
-- 3. 模型对比历史记录表 (model_compare_history)
-- 存储对比测试的历史记录
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `model_compare_history` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `task_id` VARCHAR(64) NOT NULL COMMENT '任务ID',
    `system_prompt` TEXT DEFAULT NULL COMMENT '系统提示词',
    `user_prompt` TEXT NOT NULL COMMENT '用户提示词',
    `temperature` DECIMAL(3,2) DEFAULT NULL COMMENT '温度参数',
    `max_tokens` INT DEFAULT NULL COMMENT '最大 Token 数',
    `timeout` INT DEFAULT NULL COMMENT '超时时间（秒）',
    `model_ids` JSON NOT NULL COMMENT '测试的模型ID列表',
    `api_config_id` INT DEFAULT NULL COMMENT '使用的 API 配置ID',
    `total_models` INT NOT NULL DEFAULT 0 COMMENT '测试模型总数',
    `success_count` INT NOT NULL DEFAULT 0 COMMENT '成功数量',
    `failed_count` INT NOT NULL DEFAULT 0 COMMENT '失败数量',
    `avg_latency_ms` INT DEFAULT NULL COMMENT '平均响应延迟',
    `total_tokens` INT NOT NULL DEFAULT 0 COMMENT '总 Token 使用量',
    `total_cost_usd` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '总费用（美元）',
    `total_cost_cny` DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT '总费用（人民币）',
    `user_id` VARCHAR(64) DEFAULT NULL COMMENT '用户ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `completed_at` DATETIME DEFAULT NULL COMMENT '完成时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_task_id` (`task_id`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型对比历史记录表';


-- ----------------------------------------------------------------------------
-- 4. 模型对比结果详情表 (model_compare_result)
-- 存储每次对比测试的详细结果
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `model_compare_result` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `history_id` BIGINT NOT NULL COMMENT '关联的历史记录ID',
    `model_id` VARCHAR(64) NOT NULL COMMENT '模型ID',
    `model_name` VARCHAR(64) NOT NULL COMMENT '模型显示名称',
    `provider` VARCHAR(32) NOT NULL COMMENT '提供商',
    `status` VARCHAR(16) NOT NULL COMMENT '状态: success / error / timeout',
    `response` TEXT DEFAULT NULL COMMENT '模型响应内容',
    `thinking_content` TEXT DEFAULT NULL COMMENT '思考内容（如支持）',
    `prompt_tokens` INT NOT NULL DEFAULT 0 COMMENT '输入 Token 数',
    `completion_tokens` INT NOT NULL DEFAULT 0 COMMENT '输出 Token 数',
    `total_tokens` INT NOT NULL DEFAULT 0 COMMENT '总 Token 数',
    `latency_ms` INT DEFAULT NULL COMMENT '响应延迟（毫秒）',
    `cost_usd` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '费用（美元）',
    `cost_cny` DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT '费用（人民币）',
    `error` TEXT DEFAULT NULL COMMENT '错误信息',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_history_id` (`history_id`),
    INDEX `idx_model_id` (`model_id`),
    CONSTRAINT `fk_result_history` FOREIGN KEY (`history_id`) 
        REFERENCES `model_compare_history` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型对比结果详情表';


-- ============================================================================
-- 使用说明：
-- 
-- 1. 先创建 API 配置（model_compare_api_config）
--    - 配置第三方服务商的 API Key 和 URL
--    - api_type 设置为 'generic' 表示通用 OpenAI 兼容格式
--    
-- 2. 再创建模型配置（model_compare_model）
--    - 关联对应的 api_config_id
--    - 设置模型的参数（如 use_max_completion_tokens）
--
-- 3. 示例配置（需要替换实际的 API Key）：
-- ============================================================================

-- 示例：创建一个中转服务商的 API 配置
-- INSERT INTO `model_compare_api_config` 
--     (`name`, `provider`, `api_type`, `api_key`, `api_url`, `description`, `is_default`)
-- VALUES
--     ('XX中转服务', 'XX Provider', 'generic', 'sk-your-api-key', 
--      'https://api.xxx.com/v1/chat/completions', '第三方中转服务', 1);

-- 示例：创建模型配置并关联 API 配置
-- INSERT INTO `model_compare_model` 
--     (`model_id`, `name`, `provider`, `description`, `max_tokens`, 
--      `supports_streaming`, `supports_thinking`, `use_max_completion_tokens`,
--      `input_price_per_1m`, `output_price_per_1m`, `api_config_id`, `sort_order`)
-- VALUES
--     ('gpt-4o', 'GPT-4o', 'OpenAI', 'OpenAI 最新多模态模型', 16384, 
--      1, 0, 0, 2.500000, 10.000000, 1, 10);

-- ============================================================================
-- 注意事项：
-- 1. 执行此脚本前，请确保数据库已创建
-- 2. API Key 是敏感信息，生产环境建议加密存储
-- 3. 如需从旧版本升级，请先备份数据再执行迁移脚本
-- 4. 模型必须关联有效的 api_config_id 才能进行测试
-- ============================================================================
