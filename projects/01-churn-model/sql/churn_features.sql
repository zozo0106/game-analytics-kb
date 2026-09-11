-- ============================================================
--  流失预测 · 特征提取 SQL
--  思路：把"逐日明细"压成"一人一行"的特征宽表
--  窗口口径：
--    特征窗口 = [2026-01-01, cutoff)，cutoff = 标签窗口首日 2026-02-23
--    d7  = cutoff - 7d  （近 7 天）
--    d14 = cutoff - 14d （前 7 天，用于算趋势）
--    d30 = cutoff - 30d
--  占位符 {CUTOFF}/{D7}/{D14}/{D30} 由 build_features.py 注入
-- ============================================================

WITH obs AS (   -- 只取特征窗口内的明细（严禁碰标签窗口，防泄露）
    SELECT user_id, date, logins, session_minutes, matches, social_actions, level_end
    FROM user_daily
    WHERE date < '{CUTOFF}'
),

per_user AS (   -- 一人一行：把明细聚合
    SELECT
        user_id,
        MAX(CASE WHEN logins > 0 THEN date END)                             AS last_active_date,
        SUM(logins)                                                          AS logins_total,
        SUM(CASE WHEN logins > 0 THEN 1 ELSE 0 END)                          AS active_days,
        -- 近 7 天 / 前 7 天 / 近 30 天 登录数（趋势是流失最强先行信号）
        SUM(CASE WHEN date >= '{D7}'  THEN logins ELSE 0 END)                AS logins_7d,
        SUM(CASE WHEN date >= '{D14}' AND date < '{D7}' THEN logins ELSE 0 END) AS logins_prev7d,
        SUM(CASE WHEN date >= '{D30}' THEN logins ELSE 0 END)                AS logins_30d,
        -- 深度与社交
        SUM(CASE WHEN date >= '{D7}' THEN session_minutes ELSE 0 END)        AS minutes_7d,
        SUM(CASE WHEN date >= '{D7}' THEN matches ELSE 0 END)                AS matches_7d,
        SUM(CASE WHEN date >= '{D7}' THEN social_actions ELSE 0 END)         AS social_7d,
        SUM(CASE WHEN date >= '{D30}' THEN social_actions ELSE 0 END)        AS social_30d,
        MAX(level_end)                                                       AS level_max
    FROM obs
    GROUP BY user_id
),

level_ref AS (  -- 14 天前的等级 → 用于算"进度增量"
    SELECT user_id, MAX(level_end) AS level_14d
    FROM obs
    WHERE date <= '{D14}'
    GROUP BY user_id
)

SELECT
    p.user_id,
    p.logins_total,
    p.active_days,
    p.logins_7d,
    p.logins_prev7d,
    p.logins_7d - p.logins_prev7d                                            AS login_trend,
    p.logins_30d,
    ROUND(p.logins_30d * 1.0 / 30, 3)                                        AS login_rate_30d,
    -- 距今最近一次活跃天数（recency，流失最直观的指标）
    CAST(julianday('{CUTOFF}') - julianday(p.last_active_date) AS INT)       AS recency_days,
    p.minutes_7d,
    ROUND(p.minutes_7d * 1.0 / 7, 1)                                         AS avg_minutes_7d,
    p.matches_7d,
    p.social_7d,
    p.social_30d,
    ROUND(CASE WHEN p.logins_30d > 0
               THEN p.social_30d * 1.0 / p.logins_30d ELSE 0 END, 3)         AS social_per_login,
    p.level_max,
    p.level_max - COALESCE(l.level_14d, 0)                                   AS level_gain_14d
FROM per_user p
LEFT JOIN level_ref l ON l.user_id = p.user_id
;
