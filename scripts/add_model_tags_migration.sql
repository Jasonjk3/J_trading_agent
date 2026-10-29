-- ============================================================================
-- 模型管理优化：添加标签功能
-- 1. 在模型表中添加 tags 字段
-- 2. 创建标签管理表
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. 在模型表中添加 tags 字段
-- ----------------------------------------------------------------------------
ALTER TABLE `model_compare_model` 
ADD COLUMN `tags` JSON DEFAULT NULL COMMENT '标签列表（JSON数组，如 ["对话", "视频", "视觉"]）' 
AFTER `custom_params`;

-- ----------------------------------------------------------------------------
-- 2. 创建标签管理表 (model_tag)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `model_tag` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name` VARCHAR(32) NOT NULL COMMENT '标签名称（如：对话、视频、视觉）',
    `color` VARCHAR(16) DEFAULT NULL COMMENT '标签颜色（可选，用于UI显示）',
    `description` VARCHAR(256) DEFAULT NULL COMMENT '标签描述',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序权重',
    `is_active` TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_name` (`name`),
    INDEX `idx_is_active` (`is_active`),
    INDEX `idx_sort_order` (`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型标签管理表';

-- ----------------------------------------------------------------------------
-- 3. 插入示例标签
-- ----------------------------------------------------------------------------
INSERT INTO `model_tag` (`name`, `description`, `sort_order`) VALUES
    ('对话', '适用于对话场景的模型', 1),
    ('视频', '适用于视频处理场景的模型', 2),
    ('视觉', '适用于视觉识别场景的模型', 3)
ON DUPLICATE KEY UPDATE `name` = `name`;

-- ============================================================================
-- 使用说明：
-- 
-- 1. 执行此脚本后，模型表将支持 tags 字段（JSON数组）
-- 2. 标签管理表用于统一管理可用的标签
-- 3. 示例标签已自动插入，可根据需要修改或删除
-- ============================================================================
