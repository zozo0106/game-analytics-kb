-- ============================================================
--  分日趋势表（用于新奇效应 / 长期效应观察）
--  每天一行：分组的样本量、活跃率、人均对局、人均付费
-- ============================================================
SELECT
    d.day,
    u.group_name                                        AS group_name,
    COUNT(*)                                            AS users,
    ROUND(AVG(d.active), 4)                             AS active_rate,
    ROUND(AVG(d.matches), 4)                            AS matches_per_user,
    ROUND(AVG(d.revenue), 4)                            AS revenue_per_user
FROM experiment_daily d
JOIN experiment_users u ON u.user_id = d.user_id
GROUP BY d.day, u.group_name
ORDER BY d.day, u.group_name;
