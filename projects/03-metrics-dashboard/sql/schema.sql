-- schema.sql —— 看板底表 DDL（SQLite）
-- 说明：本地用 SQLite 模拟数仓 ODS 层，指标计算全部用真实 SQL 表达。

DROP TABLE IF EXISTS daily_fact;
CREATE TABLE daily_fact (
    date         TEXT    NOT NULL,   -- 自然日
    channel      TEXT    NOT NULL,   -- 获客渠道（自然量 / 应用商店 / 买量-信息流 / 买量-KOL）
    device       TEXT    NOT NULL,   -- 机型（iOS / Android）
    region       TEXT    NOT NULL,   -- 地域（华东 / 华北 / 华南 / 西部）
    new_users    INTEGER NOT NULL,   -- 当日新增用户（DNU）
    active_users INTEGER NOT NULL,   -- 当日活跃用户（DAU）
    sessions     INTEGER NOT NULL,   -- 当日启动次数
    play_minutes REAL    NOT NULL,   -- 当日游玩总时长（分钟）
    payers       INTEGER NOT NULL,   -- 当日付费人数
    revenue      REAL    NOT NULL    -- 当日流水（元）
);
CREATE INDEX idx_fact_date    ON daily_fact(date);
CREATE INDEX idx_fact_channel ON daily_fact(channel);

DROP TABLE IF EXISTS cohort_retention;
CREATE TABLE cohort_retention (
    install_date TEXT PRIMARY KEY,   -- 新增（安装）批次日
    new_users    INTEGER NOT NULL,   -- 当日新增用户数
    retained_d1  INTEGER NOT NULL,   -- 次留人数
    retained_d7  INTEGER NOT NULL,   -- 7 日留存人数
    retained_d30 INTEGER NOT NULL    -- 30 日留存人数
);
