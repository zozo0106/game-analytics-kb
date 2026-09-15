-- daily_kpi.sql —— 日级 KPI 宽表（看板核心）
-- 输入：daily_fact（明细）+ cohort_retention（新增留存）
-- 输出：date, 规模/参与/变现指标 + 环比 + 7 日均线 + 留存
-- 口径与 ../../docs/02-metrics/metric-dictionary.md 对齐

WITH daily AS (
    SELECT date,
           SUM(active_users) AS dau,
           SUM(new_users)    AS dnu,
           SUM(sessions)     AS sessions,
           SUM(play_minutes) AS play_minutes,
           SUM(payers)       AS payers,
           SUM(revenue)      AS revenue
    FROM daily_fact
    GROUP BY date
)
SELECT
    d.date,
    d.dau,
    d.dnu,
    d.payers,
    ROUND(d.revenue, 2)                       AS revenue,
    d.sessions,
    ROUND(d.play_minutes, 1)                  AS play_minutes,

    -- ---- 变现指标（分子分母同口径，避免"同名不同义"）----
    ROUND(d.revenue / d.dau, 4)               AS arpu,           -- 每活跃用户收入
    ROUND(d.revenue / NULLIF(d.payers, 0), 3) AS arppu,          -- 每付费用户收入
    ROUND(100.0 * d.payers / d.dau, 3)        AS pay_rate_pct,   -- 付费率 %

    -- ---- 参与指标 ----
    ROUND(d.play_minutes / d.dau, 2)          AS minutes_per_dau,
    ROUND(1.0 * d.sessions / d.dau, 3)        AS sessions_per_dau,

    -- ---- 增长结构 ----
    ROUND(100.0 * d.dnu / d.dau, 3)           AS new_ratio_pct,  -- 新增占活跃比 %

    -- ---- 新增批次留存（左连接安装日）----
    ROUND(100.0 * c.retained_d1  / NULLIF(c.new_users, 0), 2) AS d1_ret_pct,
    ROUND(100.0 * c.retained_d7  / NULLIF(c.new_users, 0), 2) AS d7_ret_pct,
    ROUND(100.0 * c.retained_d30 / NULLIF(c.new_users, 0), 2) AS d30_ret_pct,

    -- ---- 环比（前一日）----
    ROUND(100.0 * (d.dau     - LAG(d.dau)     OVER w) / LAG(d.dau)     OVER w, 2) AS dau_dod_pct,
    ROUND(100.0 * (d.revenue - LAG(d.revenue) OVER w) / LAG(d.revenue) OVER w, 2) AS revenue_dod_pct,

    -- ---- 7 日移动平均（去噪看趋势）----
    ROUND(AVG(d.dau)     OVER w7, 1) AS dau_ma7,
    ROUND(AVG(d.revenue) OVER w7, 1) AS revenue_ma7
FROM daily d
LEFT JOIN cohort_retention c ON c.install_date = d.date
WINDOW
    w  AS (ORDER BY d.date),
    w7 AS (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
ORDER BY d.date;
