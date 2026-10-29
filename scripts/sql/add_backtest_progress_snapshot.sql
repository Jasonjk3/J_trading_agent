-- 回测运行中进度快照（模拟时钟、步进、livePreview 等）
-- 若列已存在会报错，可忽略或改用: python scripts/migrate_add_backtest_progress_snapshot.py
ALTER TABLE backtest_tasks
  ADD COLUMN progress_snapshot JSON NULL COMMENT '运行中进度快照' AFTER progress;
