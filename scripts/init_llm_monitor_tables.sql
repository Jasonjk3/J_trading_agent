-- ============================================================================
-- LLM 监控系统数据库初始化脚本
-- 创建时间：2026-01-30
-- 说明：包含 LLM 调用日志表、每日统计表、模型费用配置表、预警相关表
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. LLM 调用日志表 (llm_usage_log)
-- 记录每一次 LLM API 调用的详细信息
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `llm_usage_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    `request_id` VARCHAR(64) NOT NULL COMMENT '请求唯一标识（UUID）',
    `model_name` VARCHAR(64) NOT NULL COMMENT '模型名称（如 deepseek-chat, gpt-4）',
    `model_provider` VARCHAR(32) NOT NULL COMMENT '提供商（deepseek, openai）',
    `agent_name` VARCHAR(128) DEFAULT NULL COMMENT '调用的 Agent 名称',
    `task_type` VARCHAR(64) DEFAULT NULL COMMENT '任务类型（chat, analysis, extraction 等）',
    `prompt_tokens` INT NOT NULL DEFAULT 0 COMMENT '输入 Token 数',
    `completion_tokens` INT NOT NULL DEFAULT 0 COMMENT '输出 Token 数',
    `total_tokens` INT NOT NULL DEFAULT 0 COMMENT '总 Token 数',
    `cost_usd` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '费用（美元）',
    `cost_cny` DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT '费用（人民币）',
    `response_time_ms` INT NOT NULL DEFAULT 0 COMMENT '响应时间（毫秒）',
    `status` VARCHAR(16) NOT NULL DEFAULT 'success' COMMENT '状态（success, failed, timeout）',
    `error_message` TEXT DEFAULT NULL COMMENT '错误信息（如有）',
    `user_id` VARCHAR(64) DEFAULT NULL COMMENT '用户标识（可选）',
    `session_id` VARCHAR(64) DEFAULT NULL COMMENT '会话标识（可选）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `extra_data` JSON DEFAULT NULL COMMENT '扩展字段（存储其他元数据）',
    PRIMARY KEY (`id`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_model_name` (`model_name`),
    INDEX `idx_agent_name` (`agent_name`),
    INDEX `idx_user_session` (`user_id`, `session_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_request_id` (`request_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LLM 调用日志表';


-- ----------------------------------------------------------------------------
-- 2. 每日统计表 (llm_daily_stats)
-- 预聚合的每日统计数据，用于快速查询报表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `llm_daily_stats` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `stat_date` DATE NOT NULL COMMENT '统计日期',
    `model_name` VARCHAR(64) NOT NULL COMMENT '模型名称',
    `agent_name` VARCHAR(128) DEFAULT '' COMMENT 'Agent 名称（空字符串表示汇总）',
    `total_requests` INT NOT NULL DEFAULT 0 COMMENT '总请求数',
    `success_requests` INT NOT NULL DEFAULT 0 COMMENT '成功请求数',
    `failed_requests` INT NOT NULL DEFAULT 0 COMMENT '失败请求数',
    `total_prompt_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT '总输入 Token',
    `total_completion_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT '总输出 Token',
    `total_tokens` BIGINT NOT NULL DEFAULT 0 COMMENT '总 Token',
    `total_cost_usd` DECIMAL(12,6) NOT NULL DEFAULT 0.000000 COMMENT '总费用（美元）',
    `total_cost_cny` DECIMAL(12,4) NOT NULL DEFAULT 0.0000 COMMENT '总费用（人民币）',
    `avg_response_time_ms` INT NOT NULL DEFAULT 0 COMMENT '平均响应时间',
    `p50_response_time_ms` INT NOT NULL DEFAULT 0 COMMENT 'P50 响应时间',
    `p99_response_time_ms` INT NOT NULL DEFAULT 0 COMMENT 'P99 响应时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_date_model_agent` (`stat_date`, `model_name`, `agent_name`),
    INDEX `idx_stat_date` (`stat_date`),
    INDEX `idx_model_name` (`model_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LLM 每日统计表';


-- ----------------------------------------------------------------------------
-- 3. 模型费用配置表 (llm_cost_config)
-- 存储各模型的 Token 单价配置
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `llm_cost_config` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `model_name` VARCHAR(64) NOT NULL COMMENT '模型名称',
    `provider` VARCHAR(32) NOT NULL COMMENT '提供商',
    `input_price_per_1m` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '输入 Token 单价（$/1M tokens）',
    `output_price_per_1m` DECIMAL(10,6) NOT NULL DEFAULT 0.000000 COMMENT '输出 Token 单价（$/1M tokens）',
    `currency` VARCHAR(8) NOT NULL DEFAULT 'USD' COMMENT '货币单位（USD）',
    `exchange_rate` DECIMAL(8,4) NOT NULL DEFAULT 7.2500 COMMENT '美元兑人民币汇率',
    `effective_date` DATE NOT NULL COMMENT '生效日期',
    `is_active` TINYINT NOT NULL DEFAULT 1 COMMENT '是否生效（1=是，0=否）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_model_provider_date` (`model_name`, `provider`, `effective_date`),
    INDEX `idx_model_name` (`model_name`),
    INDEX `idx_provider` (`provider`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型费用配置表';


-- ----------------------------------------------------------------------------
-- 4. 预警规则表 (llm_budget_alert_rule)
-- 存储预警配置
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `llm_budget_alert_rule` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `rule_name` VARCHAR(64) NOT NULL COMMENT '规则名称',
    `alert_type` VARCHAR(32) NOT NULL COMMENT '预警类型（daily_cost/monthly_cost/single_request）',
    `threshold_value` DECIMAL(12,4) NOT NULL COMMENT '阈值（人民币）',
    `model_name` VARCHAR(64) DEFAULT NULL COMMENT '模型名称（可选，为空表示全部）',
    `agent_name` VARCHAR(128) DEFAULT NULL COMMENT 'Agent 名称（可选，为空表示全部）',
    `notify_channels` JSON NOT NULL COMMENT '通知渠道配置（飞书webhook/邮件）',
    `is_active` TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    `cooldown_minutes` INT NOT NULL DEFAULT 60 COMMENT '冷却时间（分钟），避免重复告警',
    `last_triggered_at` DATETIME DEFAULT NULL COMMENT '上次触发时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_alert_type` (`alert_type`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='预警规则表';


-- ----------------------------------------------------------------------------
-- 5. 预警历史表 (llm_budget_alert_history)
-- 记录预警触发历史
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `llm_budget_alert_history` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `rule_id` INT NOT NULL COMMENT '关联规则ID',
    `alert_type` VARCHAR(32) NOT NULL COMMENT '预警类型',
    `current_value` DECIMAL(12,4) NOT NULL COMMENT '当前值',
    `threshold_value` DECIMAL(12,4) NOT NULL COMMENT '阈值',
    `alert_message` TEXT NOT NULL COMMENT '预警消息内容',
    `notify_status` VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '通知状态（pending/success/failed）',
    `notify_result` JSON DEFAULT NULL COMMENT '通知结果详情',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '触发时间',
    PRIMARY KEY (`id`),
    INDEX `idx_rule_id` (`rule_id`),
    INDEX `idx_alert_type` (`alert_type`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_notify_status` (`notify_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='预警历史表';


-- ----------------------------------------------------------------------------
-- 6. 初始化默认费用配置数据
-- 价格数据参考各厂商官方定价（2026年1月）
-- ----------------------------------------------------------------------------
INSERT INTO `llm_cost_config` 
    (`model_name`, `provider`, `input_price_per_1m`, `output_price_per_1m`, `currency`, `exchange_rate`, `effective_date`, `is_active`)
VALUES
    -- DeepSeek 模型
    ('deepseek-chat', 'deepseek', 0.14, 0.28, 'USD', 7.25, '2026-01-01', 1),
    ('deepseek-reasoner', 'deepseek', 0.55, 2.19, 'USD', 7.25, '2026-01-01', 1),
    
    -- OpenAI 模型
    ('gpt-4o', 'openai', 2.50, 10.00, 'USD', 7.25, '2026-01-01', 1),
    ('gpt-4o-mini', 'openai', 0.15, 0.60, 'USD', 7.25, '2026-01-01', 1),
    ('gpt-4-turbo', 'openai', 10.00, 30.00, 'USD', 7.25, '2026-01-01', 1),
    ('gpt-3.5-turbo', 'openai', 0.50, 1.50, 'USD', 7.25, '2026-01-01', 1),
    
    -- OpenAI o1 系列（推理模型）
    ('o1', 'openai', 15.00, 60.00, 'USD', 7.25, '2026-01-01', 1),
    ('o1-mini', 'openai', 3.00, 12.00, 'USD', 7.25, '2026-01-01', 1)
ON DUPLICATE KEY UPDATE
    `input_price_per_1m` = VALUES(`input_price_per_1m`),
    `output_price_per_1m` = VALUES(`output_price_per_1m`),
    `exchange_rate` = VALUES(`exchange_rate`),
    `updated_at` = CURRENT_TIMESTAMP;


-- ============================================================================
-- 说明：
-- 1. 执行此脚本前，请确保数据库已创建
-- 2. 所有表使用 utf8mb4 字符集以支持完整的 Unicode
-- 3. 费用配置数据可根据实际价格调整
-- 4. exchange_rate 汇率需要定期更新
-- ============================================================================
