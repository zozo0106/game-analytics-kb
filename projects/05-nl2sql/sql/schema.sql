-- ============================================================
-- PRJ-5 NL2SQL · 游戏分析主题库 Schema (SQLite)
-- 设计原则：贴近真实数仓的 4 张核心表，覆盖"用户-行为-付费-商品"
-- ============================================================

DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS daily_active;
DROP TABLE IF EXISTS purchases;
DROP TABLE IF EXISTS products;

-- 用户维度表
CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY,
    register_date TEXT NOT NULL,          -- YYYY-MM-DD
    channel       TEXT NOT NULL,          -- 自然量 / 买量-抖音 / 买量-腾讯 / 应用商店
    country       TEXT NOT NULL,          -- CN / US / JP / KR / SEA
    level         INTEGER NOT NULL,       -- 当前等级 1-60
    vip_level     INTEGER NOT NULL        -- 0-5
);

-- 日活明细表（玩家 x 天）
CREATE TABLE daily_active (
    user_id      INTEGER NOT NULL,
    log_date     TEXT NOT NULL,           -- YYYY-MM-DD
    sessions     INTEGER NOT NULL,        -- 当日会话数
    play_minutes REAL NOT NULL,           -- 当日时长（分钟）
    level_end    INTEGER NOT NULL,        -- 当日结束等级
    PRIMARY KEY (user_id, log_date)
);

-- 付费订单表
CREATE TABLE purchases (
    order_id   INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    order_date TEXT NOT NULL,             -- YYYY-MM-DD
    product_id INTEGER NOT NULL,
    amount     REAL NOT NULL,             -- 实付金额（元）
    currency   TEXT NOT NULL DEFAULT 'CNY'
);

-- 商品维度表
CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    product_type TEXT NOT NULL,           -- 礼包 / 月卡 / 皮肤 / 道具
    price        REAL NOT NULL
);

CREATE INDEX idx_da_date ON daily_active(log_date);
CREATE INDEX idx_da_user ON daily_active(user_id);
CREATE INDEX idx_pu_date ON purchases(order_date);
CREATE INDEX idx_pu_user ON purchases(user_id);
CREATE INDEX idx_us_reg  ON users(register_date);
