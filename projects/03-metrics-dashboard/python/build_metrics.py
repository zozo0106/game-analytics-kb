#!/usr/bin/env python3
"""
build_metrics.py —— 明细 CSV → SQLite → 跑 SQL → 指标宽表
================================================================
把"数仓指标层"用真实 SQL 表达：本地建 SQLite，跑 sql/ 下的指标脚本。
SQL 不是摆设 —— clone 下来跑一遍，看到的就是生产同款口径。

输入：data/daily_fact.csv, data/cohort_retention.csv
输出：data/metrics_daily.csv    （日级 KPI 宽表，看板核心）
      data/metrics_segment.csv  （日期 × 渠道 KPI，供下钻）

运行：python python/build_metrics.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SQL = ROOT / "sql"
DB = DATA / "metrics.db"

OUTPUTS = {
    "daily_kpi.sql": "metrics_daily.csv",
    "segment_kpi.sql": "metrics_segment.csv",
}


def load_sqlite() -> sqlite3.Connection:
    fact = pd.read_csv(DATA / "daily_fact.csv")
    cohort = pd.read_csv(DATA / "cohort_retention.csv")

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript((SQL / "schema.sql").read_text(encoding="utf-8"))
    fact.to_sql("daily_fact", con, if_exists="append", index=False)
    cohort.to_sql("cohort_retention", con, if_exists="append", index=False)
    return con


def main() -> None:
    con = load_sqlite()
    print(f"✅ 已载入 SQLite：{DB.name}")

    for sql_file, out_name in OUTPUTS.items():
        query = (SQL / sql_file).read_text(encoding="utf-8")
        df = pd.read_sql_query(query, con)
        df.to_csv(DATA / out_name, index=False)
        print(f"   {sql_file:20s} → data/{out_name:22s} {df.shape[0]:>6,} 行 × {df.shape[1]} 列")

    con.close()
    print("✅ 指标层计算完成")


if __name__ == "__main__":
    main()
