-- ============================================================
--  用户级指标宽表（一人一行）—— 实验期前 7 天口径
--  思路与项目 01 一致：把"每日明细"用 CASE + 聚合压成"一人一行"
--  口径声明（先定口径，再做检验）：
--    主指标   retained_d7  = 第 7 天是否活跃（0/1）
--    次指标   matches_7d   = 前 7 天对局总数
--             revenue_7d   = 前 7 天付费总额
--             payer_7d     = 前 7 天是否有付费（0/1）
--  注：不写死日期，用 day 相对口径，改窗口只改这里一个数字
-- ============================================================
WITH win AS (           -- 只看前 7 天，避免实验后期数据污染主指标
    SELECT d.user_id, d.day, d.active, d.matches, d.revenue
    FROM experiment_daily d
    WHERE d.day <= 7
),

per_user AS (           -- 一人一行
    SELECT
        user_id,
        MAX(CASE WHEN day = 7 THEN active END)          AS retained_d7,
        SUM(active)                                     AS active_days_7d,
        SUM(matches)                                    AS matches_7d,
        ROUND(SUM(revenue), 2)                          AS revenue_7d,
        MAX(CASE WHEN revenue > 0 THEN 1 ELSE 0 END)    AS payer_7d
    FROM win
    GROUP BY user_id
)

SELECT
    u.user_id,
    u.group_name                                  AS group_name,
    u.channel,
    u.device,
    u.pre_active_days_14d,
    u.pre_matches_14d,
    u.pre_revenue_14d,
    p.retained_d7,
    p.active_days_7d,
    p.matches_7d,
    p.revenue_7d,
    p.payer_7d
FROM experiment_users u
JOIN per_user p ON p.user_id = u.user_id;
