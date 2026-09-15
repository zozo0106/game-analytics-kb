-- ============================================================
--  实验数据表结构（SQLite / 可移植到 Hive / MySQL）
--  与分析无关，仅用于 build_features.py 在本地 SQLite 里重放
-- ============================================================

DROP TABLE IF EXISTS experiment_users;
CREATE TABLE experiment_users (
    user_id             INTEGER PRIMARY KEY,
    group_name          TEXT    NOT NULL,   -- control / treatment
    channel             TEXT    NOT NULL,   -- 自然量 / 买量
    device              TEXT    NOT NULL,   -- iOS / Android
    pre_active_days_14d INTEGER NOT NULL,   -- 实验前 14 天活跃天数
    pre_matches_14d     INTEGER NOT NULL,   -- 实验前 14 天对局数（CUPED 协变量）
    pre_revenue_14d     REAL    NOT NULL    -- 实验前 14 天付费金额
);

DROP TABLE IF EXISTS experiment_daily;
CREATE TABLE experiment_daily (
    user_id INTEGER NOT NULL,   -- 关联 experiment_users
    day     INTEGER NOT NULL,   -- 实验第几天 1..14
    group_name TEXT NOT NULL,
    active  INTEGER NOT NULL,   -- 当天是否活跃 0/1
    matches INTEGER NOT NULL,   -- 当天对局数
    revenue REAL    NOT NULL    -- 当天付费金额
);

CREATE INDEX idx_daily_user ON experiment_daily(user_id, day);
