-- segment_kpi.sql —— 分渠道日级 KPI（看板下钻用）
-- 输出：date × channel 的规模/变现指标，供看板按渠道拆解

SELECT
    date,
    channel,
    SUM(active_users)                          AS dau,
    SUM(new_users)                             AS dnu,
    SUM(payers)                                AS payers,
    ROUND(SUM(revenue), 2)                     AS revenue,
    ROUND(SUM(revenue) / SUM(active_users), 4) AS arpu,
    ROUND(100.0 * SUM(payers) / SUM(active_users), 3) AS pay_rate_pct
FROM daily_fact
GROUP BY date, channel
ORDER BY date, channel;
