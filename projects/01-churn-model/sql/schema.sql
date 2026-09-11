-- ============================================================
--  表结构定义（可移植写法）
--  本项目用 SQLite 演示，可无缝搬到 MySQL 8+ / Hive / Spark SQL / DuckDB
-- ============================================================

DROP TABLE IF EXISTS user_daily;
DROP TABLE IF EXISTS user_profile;
DROP TABLE IF EXISTS purchases;
DROP TABLE IF EXISTS labels;

-- 用户日活明细（分析的主战场：宽表 + 一天一行）
CREATE TABLE user_daily (
    user_id         VARCHAR(16)  NOT NULL,   -- Hive: string
    date            DATE         NOT NULL,
    logins          INT          NOT NULL,   -- 当日登录次数
    session_minutes INT          NOT NULL,   -- 当日在线时长（分钟）
    matches         INT          NOT NULL,   -- 当日对局数
    social_actions  INT          NOT NULL,   -- 当日社交行为数（组队/聊天/公会）
    level_end       INT          NOT NULL,   -- 当日结束时的等级
    PRIMARY KEY (user_id, date)
);

-- 用户档案（维度表）
CREATE TABLE user_profile (
    user_id       VARCHAR(16) NOT NULL PRIMARY KEY,
    register_date DATE        NOT NULL,
    channel       VARCHAR(32) NOT NULL,      -- 获客渠道
    device        VARCHAR(16) NOT NULL,
    country       VARCHAR(16) NOT NULL,
    is_payer      INT         NOT NULL       -- 是否付费用户 0/1
);

-- 付费流水（事实表）
CREATE TABLE purchases (
    user_id VARCHAR(16) NOT NULL,
    date    DATE        NOT NULL,
    amount  DECIMAL(10,2) NOT NULL
);

-- 标签（建模用；线上由标签窗口自动生成）
CREATE TABLE labels (
    user_id VARCHAR(16) NOT NULL PRIMARY KEY,
    churn   INT         NOT NULL            -- 1=标签窗口内零登录
);
