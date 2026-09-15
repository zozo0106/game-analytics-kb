#!/usr/bin/env python3
"""
02_dashboard.py —— 生成自包含静态看板
================================================================
零依赖交付：把 KPI 卡片 + 趋势图 + 渠道拆解 + 告警列表渲染成一个
**单文件 HTML**（内联 CSS/SVG，不依赖任何前端框架或 CDN），双击即可看。
再额外输出一张渠道对比 PNG，方便贴文档。

输入：data/metrics_daily.csv, data/metrics_segment.csv,
      data/summary.json, data/alerts.json
输出：assets/dashboard.html
      assets/channel_mix.png

运行：python python/02_dashboard.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

CARD_METRICS = [
    ("dau", "DAU", "{:,.0f}"),
    ("revenue", "Revenue", "{:,.0f}"),
    ("arpu", "ARPU", "{:.2f}"),
    ("pay_rate_pct", "Pay rate", "{:.2f}%"),
    ("d1_ret_pct", "D1 retention", "{:.1f}%"),
    ("minutes_per_dau", "Min / DAU", "{:.1f}"),
]


def svg_line(dates: list[str], series: dict[str, list[float]],
             alert_dates: set[str], w: int = 900, h: int = 300) -> str:
    pad_l, pad_r, pad_t, pad_b = 55, 15, 15, 30
    ys = [v for vals in series.values() for v in vals]
    lo, hi = min(ys), max(ys)
    lo, hi = lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.08
    n = len(dates)
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    px = lambda i: pad_l + iw * i / (n - 1)
    py = lambda v: pad_t + ih * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="xMidYMid meet">']
    # 异常日竖带
    for d in dates:
        if d in alert_dates:
            parts.append(f'<rect x="{px(dates.index(d)) - 1.2:.1f}" y="{pad_t}" width="2.4" '
                         f'height="{ih}" fill="#C44E52" opacity="0.18"/>')
    # 网格 + y 轴刻度
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = py(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" '
                     f'stroke="#e6e6e6" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="#888">{v:,.0f}</text>')
    # 折线
    colors = {"dau": "#4C72B0", "dau_ma7": "#DD8452"}
    for name, vals in series.items():
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
        dash = ' stroke-dasharray="5,3"' if name.endswith("ma7") else ""
        width = 2.4 if name.endswith("ma7") else 1.2
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{colors.get(name, "#333")}" '
                     f'stroke-width="{width}"{dash}/>')
    # x 轴首尾标签
    parts.append(f'<text x="{pad_l}" y="{h - 8}" font-size="11" fill="#888">{dates[0]}</text>')
    parts.append(f'<text x="{w - pad_r}" y="{h - 8}" text-anchor="end" font-size="11" '
                 f'fill="#888">{dates[-1]}</text>')
    # 图例
    parts.append(f'<text x="{pad_l + 4}" y="{pad_t + 14}" font-size="11" fill="#4C72B0">■ DAU</text>')
    parts.append(f'<text x="{pad_l + 60}" y="{pad_t + 14}" font-size="11" fill="#DD8452">■ 7-day MA</text>')
    parts.append("</svg>")
    return "".join(parts)


def build_html(df: pd.DataFrame, seg: pd.DataFrame, summary: dict,
               alerts: list[dict]) -> str:
    last = df.iloc[-1]
    alert_dates = {a["date"] for a in alerts}
    dates = df["date"].tolist()
    line = svg_line(dates, {"dau": df["dau"].tolist(), "dau_ma7": df["dau_ma7"].tolist()},
                    alert_dates)

    # KPI 卡片
    cards = []
    for key, label, fmt in CARD_METRICS:
        s = summary.get(key, {})
        wow = s.get("wow_pct")
        arrow = "▲" if (wow or 0) > 0 else ("▼" if (wow or 0) < 0 else "•")
        cls = "up" if (wow or 0) > 0 else ("down" if (wow or 0) < 0 else "flat")
        val = fmt.format(s.get("last7", last.get(key, 0)))
        cards.append(f'''<div class="card">
  <div class="k">{label}</div>
  <div class="v">{val}</div>
  <div class="d {cls}">{arrow} {wow:+.2f}% <span class="m">WoW</span></div>
</div>''')

    # 渠道拆解（最近 30 天）
    tail = seg.tail(30 * seg["channel"].nunique())
    ch = tail.groupby("channel", as_index=False).agg(
        dau=("dau", "mean"), arpu=("arpu", "mean"), pay=("pay_rate_pct", "mean"))
    ch = ch.sort_values("dau", ascending=False)
    total = ch["dau"].sum()
    rows = "".join(
        f'<tr><td>{r.channel}</td><td>{r.dau:,.0f}</td><td>{100 * r.dau / total:.1f}%</td>'
        f'<td>{r.arpu:.2f}</td><td>{r.pay:.2f}%</td></tr>'
        for r in ch.itertuples())

    # 告警列表
    al = "".join(
        f'<li><b>{a["date"]}</b> · {a["metric"]} = {a["value"]:,.2f} '
        f'<span class="tag {"hi" if a["direction"] == "高于常态" else "lo"}">{a["direction"]}</span> '
        f'<span class="z">z={a["z"]:+.1f}</span></li>' for a in alerts[:14])

    # 最近 10 天表
    cols = [("date", "Date"), ("dau", "DAU"), ("revenue", "Revenue"), ("arpu", "ARPU"),
            ("pay_rate_pct", "Pay%"), ("d1_ret_pct", "D1%"), ("dau_dod_pct", "DoD%")]
    th = "".join(f"<th>{c[1]}</th>" for c in cols)
    trs = ""
    for _, r in df.tail(10).iloc[::-1].iterrows():
        tds = ""
        for c, _ in cols:
            v = r[c]
            tds += f"<td>{v:,.2f}</td>" if isinstance(v, float) else f"<td>{v}</td>"
        trs += f"<tr>{tds}</tr>"

    return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>游戏指标体系看板 · Metrics Dashboard</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#20242c;--sub:#8a94a6;--line:#e8ebf0;
--up:#2e9e5b;--down:#c9424a;--accent:#4C72B0;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1040px;margin:0 auto;padding:28px 20px 60px}}
header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
h1{{font-size:20px;margin:0}}
.sub{{color:var(--sub);font-size:12px}}
.cards{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:22px 0}}
@media(max-width:820px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}}
.card .k{{color:var(--sub);font-size:12px}}
.card .v{{font-size:22px;font-weight:600;margin:4px 0}}
.card .d{{font-size:12px}}
.card .m{{color:var(--sub)}}
.up{{color:var(--up)}} .down{{color:var(--down)}} .flat{{color:var(--sub)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin-bottom:18px}}
h2{{font-size:15px;margin:0 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:right;padding:7px 8px;border-bottom:1px solid var(--line)}}
th:first-child,td:first-child{{text-align:left}}
th{{color:var(--sub);font-weight:600}}
ul{{margin:0;padding-left:18px}} li{{margin:5px 0;font-size:13px}}
.tag{{font-size:11px;padding:1px 6px;border-radius:6px;color:#fff}}
.tag.hi{{background:var(--up)}} .tag.lo{{background:var(--down)}}
.z{{color:var(--sub);font-size:12px}}
footer{{color:var(--sub);font-size:12px;text-align:center;margin-top:10px}}
</style></head><body><div class="wrap">
<header>
  <div>
    <h1>🎮 游戏指标体系看板</h1>
    <div class="sub">合成数据 · {df['date'].iloc[0]} ~ {df['date'].iloc[-1]} · {len(df)} 天 · 口径见 metric-dictionary</div>
  </div>
  <div class="sub">生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</header>

<div class="cards">{''.join(cards)}</div>

<section>
  <h2>DAU 趋势（红线竖带 = 稳健 z 异常日）</h2>
  {line}
</section>

<section>
  <h2>渠道拆解（最近 30 天均值）</h2>
  <table><thead><tr><th>Channel</th><th>DAU</th><th>Share</th><th>ARPU</th><th>Pay rate</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>

<section>
  <h2>🚨 异常告警（改进 z 分数 · 去星期季节性 · |z|&gt;3.5）</h2>
  <ul>{al}</ul>
</section>

<section>
  <h2>最近 10 天明细</h2>
  <table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>
</section>

<footer>简历大师 · metrics-dashboard · 全部为合成数据，非真实业务数据</footer>
</div></body></html>'''


CH_EN = {"自然量": "Organic", "应用商店": "AppStore",
         "买量-信息流": "Paid-Feed", "买量-KOL": "Paid-KOL"}


def plot_channel_mix(ch: pd.DataFrame) -> None:
    labels = [CH_EN.get(c, c) for c in ch["channel"]]   # 图内用英文，避免缺字
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    axes[0].bar(labels, ch["dau"] / 1000, color="#4C72B0")
    axes[0].set_title("Avg DAU by channel (last 30d, k)", loc="left", fontsize=10)
    axes[1].bar(labels, ch["arpu"], color="#DD8452")
    axes[1].set_title("ARPU by channel (last 30d, CNY)", loc="left", fontsize=10)
    for ax in axes:
        ax.grid(alpha=0.25, axis="y")
        ax.tick_params(axis="x", labelrotation=15, labelsize=9)
    fig.tight_layout()
    fig.savefig(ASSETS / "channel_mix.png", dpi=130)
    plt.close(fig)


def main() -> None:
    df = pd.read_csv(DATA / "metrics_daily.csv")
    seg = pd.read_csv(DATA / "metrics_segment.csv")
    summary = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    alerts = json.loads((DATA / "alerts.json").read_text(encoding="utf-8"))

    html = build_html(df, seg, summary, alerts)
    (ASSETS / "dashboard.html").write_text(html, encoding="utf-8")

    tail = seg.tail(30 * seg["channel"].nunique())
    ch = tail.groupby("channel", as_index=False).agg(
        dau=("dau", "mean"), arpu=("arpu", "mean"))
    plot_channel_mix(ch.sort_values("dau", ascending=False))

    print("✅ 看板已生成")
    print(f"   assets/dashboard.html   {len(html) / 1024:.1f} KB（自包含，浏览器直接打开）")
    print("   assets/channel_mix.png")


if __name__ == "__main__":
    main()
