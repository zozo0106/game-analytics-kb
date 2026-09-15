#!/usr/bin/env python3
"""
build_features.py —— 原始 CSV → SQLite → 跑 SQL → 特征宽表
================================================================
把"数仓那一段"用 SQL 表达：本地建一个 SQLite，用真实 SQL 文件提指标。
这样 SQL 不是摆设 —— clone 下来跑一遍，看到的就是生产同款口径。

输入：data/experiment_users.csv, data/experiment_daily.csv
输出：data/ab_features.csv   （一人一行）
      data/daily_trend.csv   （分日趋势）

运行：python python/build_features.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SQL = ROOT / "sql"
DB = DATA / "ab_test.db"

# 输出文件名 ← SQL 文件名（去掉 .sql）
OUTPUTS = {
    "experiment_metrics.sql": "ab_features.csv",
    "daily_trend.sql": "daily_trend.csv",
}


def load_sqlite() -> sqlite3.Connection:
    users = pd.read_csv(DATA / "experiment_users.csv")
    daily = pd.read_csv(DATA / "experiment_daily.csv")

    # 列名对齐 SQL 里的 group_name（group 是 SQL 保留字）
    users = users.rename(columns={"group": "group_name"})
    daily = daily.rename(columns={"group": "group_name"})

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript((SQL / "schema.sql").read_text(encoding="utf-8"))
    users.to_sql("experiment_users", con, if_exists="append", index=False)
    daily.to_sql("experiment_daily", con, if_exists="append", index=False)
    return con


def main() -> None:
    con = load_sqlite()
    print(f"✅ 已载入 SQLite：{DB.name}")

    for sql_file, out_name in OUTPUTS.items():
        query = (SQL / sql_file).read_text(encoding="utf-8")
        df = pd.read_sql_query(query, con)
        df.to_csv(DATA / out_name, index=False)
        print(f"   {sql_file:24s} → data/{out_name:20s} {df.shape[0]:>7,} 行 × {df.shape[1]} 列")

    con.close()
    print("✅ 特征提取完成")


if __name__ == "__main__":
    main()
