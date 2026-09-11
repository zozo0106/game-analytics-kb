#!/usr/bin/env python3
"""
流失预测建模与评估
================================================

模型：
  1) 逻辑回归（可解释、可上生产打分卡）
  2) 梯度提升树 HistGradientBoosting（性能上限）
评估：AUC / PR-AUC / KS / 十分位提升度(Lift) —— 业务真正看的是 Lift

产出：
  - data/churn_scores.csv   测试集打分 + 风险分层（可直接给运营）
  - assets/model_*.png      ROC 曲线 / Lift 图 / 特征重要性
  - data/metrics.json       指标（供报告引用）

运行：python python/02_churn_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (average_precision_score,  # noqa: E402
                             roc_auc_score, roc_curve)
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
SEED = 42

NUM_FEATURES = [
    "recency_days", "logins_7d", "login_trend", "logins_30d", "active_days",
    "avg_minutes_7d", "matches_7d", "social_7d", "social_per_login",
    "level_max", "level_gain_14d", "days_since_pay", "revenue_30d",
]
CAT_FEATURES = ["channel", "device"]


def ks_stat(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """KS = max(TPR - FPR)，风控/流失场景常用。"""
    fpr, tpr, _ = roc_curve(y_true, y_score)
    return float(np.max(tpr - fpr))


def lift_table(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """十分位提升度：把用户按风险排序分 10 组，看每组抓到多少流失用户。"""
    d = pd.DataFrame({"y": y_true, "s": y_score})
    d["decile"] = pd.qcut(d["s"].rank(method="first"), n_bins, labels=False) + 1
    d["decile"] = n_bins + 1 - d["decile"]          # 1 = 风险最高
    base = y_true.mean()
    out = d.groupby("decile").agg(samples=("y", "size"), churners=("y", "sum"))
    out["churn_rate"] = out["churners"] / out["samples"]
    out["lift"] = out["churn_rate"] / base
    out["cum_capture"] = out["churners"].cumsum() / out["churners"].sum()
    return out.reset_index()


def main() -> None:
    df = pd.read_csv(ROOT / "data" / "features.csv")

    X = df[NUM_FEATURES + CAT_FEATURES].copy()
    X = pd.get_dummies(X, columns=CAT_FEATURES, drop_first=True)
    y = df["churn"].values
    feat_names = list(X.columns)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, random_state=SEED, stratify=y
    )
    print(f"训练 {len(X_tr):,} / 测试 {len(X_te):,} | 训练流失率 {y_tr.mean():.1%}\n")

    models = {
        "LogisticRegression": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ]),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_depth=4,
            l2_regularization=1.0, random_state=SEED,
        ),
    }

    results, fitted = {}, {}
    for name, model in models.items():
        model.fit(X_tr, y_tr)
        prob = model.predict_proba(X_te)[:, 1]
        fitted[name] = (model, prob)
        results[name] = {
            "AUC": round(roc_auc_score(y_te, prob), 4),
            "PR_AUC": round(average_precision_score(y_te, prob), 4),
            "KS": round(ks_stat(y_te, prob), 4),
        }
        print(f"[{name}]  AUC={results[name]['AUC']}  PR-AUC={results[name]['PR_AUC']}  KS={results[name]['KS']}")

    # ---- 选表现最好的模型出报告 ----
    best = max(results, key=lambda k: results[k]["AUC"])
    model, prob = fitted[best]
    print(f"\n→ 主模型：{best}")

    # ---- 十分位提升表 ----
    lt = lift_table(y_te, prob)
    print("\n== 十分位提升表（1=风险最高）==")
    print(lt.round(3).to_string(index=False))
    top10 = lt.iloc[0]
    print(f"\nTop 10% 风险用户：占 {top10['samples']/len(y_te):.0%} 人群，"
          f"却覆盖 {top10['cum_capture']:.0%} 的流失用户，提升度 {top10['lift']:.2f}x")

    # ---- 图表：ROC + Lift ----
    fpr, tpr, _ = roc_curve(y_te, prob)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    ax[0].plot(fpr, tpr, color="#4C78A8", lw=2, label=f"{best} (AUC={results[best]['AUC']})")
    ax[0].plot([0, 1], [0, 1], "--", color="grey")
    ax[0].set_xlabel("False Positive Rate"); ax[0].set_ylabel("True Positive Rate")
    ax[0].set_title("ROC Curve"); ax[0].legend(loc="lower right")

    ax[1].bar(lt["decile"], lt["lift"], color="#E45756")
    ax[1].axhline(1.0, ls="--", color="grey")
    ax[1].set_xlabel("Risk decile (1 = highest)"); ax[1].set_ylabel("Lift")
    ax[1].set_title("Lift by decile")
    fig.tight_layout(); fig.savefig(ASSETS / "model_eval.png", dpi=120)

    # ---- 特征重要性 ----
    if best == "LogisticRegression":
        coefs = model.named_steps["clf"].coef_[0]
        imp = pd.Series(coefs, index=feat_names).sort_values(key=abs, ascending=False)
        imp.head(12).to_frame("coef").to_csv(ROOT / "data" / "feature_importance.csv")
    else:
        pi = permutation_importance(model, X_te, y_te, n_repeats=10,
                                    random_state=SEED, scoring="roc_auc")
        imp = pd.Series(pi.importances_mean, index=feat_names).sort_values(ascending=False)
        imp.head(12).to_frame("importance").to_csv(ROOT / "data" / "feature_importance.csv")
    print("\n== Top 特征重要性 ==")
    print(imp.head(12).round(4).to_string())

    # ---- 输出打分名单（业务可用）----
    scores = pd.DataFrame({
        "user_id": df.loc[X_te.index, "user_id"].values,
        "churn_prob": prob,
    })
    scores["risk_tier"] = pd.cut(
        scores["churn_prob"], bins=[-0.01, 0.2, 0.5, 0.8, 1.01],
        labels=["低", "中", "高", "极高"],
    )
    scores.sort_values("churn_prob", ascending=False).to_csv(
        ROOT / "data" / "churn_scores.csv", index=False)

    (ROOT / "data" / "metrics.json").write_text(json.dumps({
        "best_model": best, "models": results,
        "top10_lift": round(float(top10["lift"]), 2),
        "top10_capture": round(float(top10["cum_capture"]), 3),
        "test_churn_rate": round(float(y_te.mean()), 4),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 打分名单：data/churn_scores.csv | 指标：data/metrics.json")


if __name__ == "__main__":
    main()
