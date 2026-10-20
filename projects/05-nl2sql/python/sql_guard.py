"""
SQL 安全护栏 —— NL2SQL 上线前的最后一道闸。

为什么必须有：
    自然语言是不可信输入。用户（或注入的提示词）说出"删掉所有订单"，模型就真可能吐出 DROP TABLE。
    分析型系统里这条链路永远是：**只读账号 + 语句白名单 + 强制 LIMIT**，三层都不省。

本模块做三件事：
    1. 只允许单条 SELECT（禁 DDL/DML/多语句/注释绕过）
    2. 禁止危险函数与系统表
    3. 无 LIMIT 的明细查询自动补 LIMIT，防止把生产库拖死
"""
from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|pragma|vacuum|replace)\b",
    re.IGNORECASE,
)
FORBIDDEN_FUNCS = re.compile(r"\b(load_extension|writefile|readfile)\s*\(", re.IGNORECASE)
DANGEROUS_TABLES = re.compile(r"\b(sqlite_master|sqlite_schema|sqlite_temp_master)\b", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    pass


def validate(sql: str, max_rows: int = 1000, auto_limit: bool = True) -> str:
    s = sql.strip().rstrip(";")

    if ";" in s:
        raise UnsafeSQLError("只允许单条语句（检测到多条）")
    if "--" in s or "/*" in s:
        raise UnsafeSQLError("检测到注释，可能用于绕过检查")
    if not re.match(r"^\s*(select|with)\b", s, re.IGNORECASE):
        raise UnsafeSQLError("只允许 SELECT 查询")
    if FORBIDDEN.search(s):
        raise UnsafeSQLError(f"包含禁止关键字：{FORBIDDEN.search(s).group(0)}")
    if FORBIDDEN_FUNCS.search(s):
        raise UnsafeSQLError("包含危险函数")
    if DANGEROUS_TABLES.search(s):
        raise UnsafeSQLError("访问系统表")

    if auto_limit and "limit" not in s.lower() and "group by" not in s.lower() and "count(" not in s.lower():
        s += f"\nLIMIT {max_rows}"

    return s


if __name__ == "__main__":
    bad = [
        "DROP TABLE users",
        "SELECT * FROM users; DELETE FROM users",
        "SELECT * FROM users -- 无害的样子",
        "SELECT load_extension('evil.so')",
    ]
    for b in bad:
        try:
            validate(b)
            print("✗ 漏放行:", b)
        except UnsafeSQLError as e:
            print("✓ 拦截:", b, "->", e)

    print("✓ 放行:", validate("SELECT COUNT(*) FROM users"))
