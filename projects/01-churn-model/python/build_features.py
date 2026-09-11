#!/usr/bin/env python3
"""
构建特征表：把原始日志 → 一人一行的建模宽表
================================================

流程：
  1. 生成数据（若不存在，自动调 data/generate_data.py）
  2. 原始 CSV → 内存 SQLite（跑真实 SQL，不是假 SQL）
  3. 执行 sql/churn_features.sql 提取行为特征（窗口函数 / CASE 聚合）
  4. 补充档案维度（渠道/设备）与付费特征
  5. 落盘 features.csv，供 EDA / 建模使用

运行：python python/build_features.py
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SQL = ROOT / "sql"

CUTOFF = "2026-02-23"   # 标签窗口首日 = 特征窗口结束
D7, D14, D30 = "2026-02-16", "2026-02-09", "2026-01-24"


def ensure_data() -> None:
    if not (DATA / "user_daily.csv").exists():
        print("· 原始数据不存在，先生成…")
        subprocess.run([sys.executable, str(DATA / "generate_data.py")], check=True)


def main() -> None:
    ensure_data()

    con = sqlite3.connect(":memory:")
    con.executescript((SQL / "schema.sql").read_text(encoding="utf-8"))

    for name in ["user_daily", "user_profile", "purchases", "labels"]:
        df = pd.read_csv(DATA / f"{name}.csv")
        if name == "labels":
            df = df[["user_id", "churn"]]        # 忽略仅供自检的 _true_quit_day
        df.to_sql(name, con, if_exists="append", index=False)

    # ---- 1. 行为特征（SQL 主逻辑）----
    feat_sql = (SQL / "churn_features.sql").read_text(encoding="utf-8").format(
        CUTOFF=CUTOFF, D7=D7, D14=D14, D30=D30
    )
    feats = pd.read_sql_query(feat_sql, con)

    # ---- 2. 档案维度 + 付费特征 ----
    prof = pd.read_sql_query(
        "SELECT * FROM user_profile", con
    )
    pay = pd.read_sql_query(
        f"""
        SELECT user_id,
               COUNT(*)                                             AS pay_cnt_30d,
               SUM(CASE WHEN date >= '{CUTOFF}' THEN 0 ELSE amount END) AS revenue_total,
               SUM(CASE WHEN date >= '{D30}' THEN amount ELSE 0 END)     AS revenue_30d,
               MAX(CASE WHEN date < '{CUTOFF}' THEN date END)           AS last_pay_date
        FROM purchases
        GROUP BY user_id
        """,
        con,
    )
    lab = pd.read_sql_query("SELECT user_id, churn FROM labels", con)

    df = (
        feats.merge(prof[["user_id", "channel", "device", "country", "is_payer"]], on="user_id", how="left")
             .merge(pay, on="user_id", how="left")
             .merge(lab, on="user_id", how="left")
    )

    # 付费特征缺失填充 + 派生
    # 特征窗口内从未活跃（注册后即流失）→ recency 置为整窗长度
    df["recency_days"] = df["recency_days"].fillna(53).astype(int)
    df["pay_cnt_30d"] = df["pay_cnt_30d"].fillna(0)
    df["revenue_total"] = df["revenue_total"].fillna(0)
    df["revenue_30d"] = df["revenue_30d"].fillna(0)
    df["days_since_pay"] = (pd.Timestamp(CUTOFF) - pd.to_datetime(df["last_pay_date"])).dt.days
    df["days_since_pay"] = df["days_since_pay"].fillna(9999).clip(upper=9999)

    df.to_csv(ROOT / "data" / "features.csv", index=False)

    print(f"✅ 特征表写入 data/features.csv")
    print(f"   样本数 : {len(df):,}")
    print(f"   特征数 : {df.shape[1] - 2}  （不含 user_id / churn）")
    print(f"   流失率 : {df['churn'].mean():.1%}")
    print(f"   列     : {', '.join(df.columns)}")
    con.close()


if __name__ == "__main__":
    main()
