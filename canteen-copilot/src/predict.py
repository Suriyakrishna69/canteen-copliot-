"""
Recurrence Prediction Engine for Canteen Copilot.
"""

from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.ensemble import HistGradientBoostingClassifier

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except Exception:
    HAS_LIGHTGBM = False


def build_weekly_panel(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "date" in df.columns:
        df["dt"] = pd.to_datetime(df["date"])
        if "week" not in df.columns:
            min_date = df["dt"].min()
            df["week"] = ((df["dt"] - min_date).dt.days // 7) + 1
        if "day_of_week" not in df.columns:
            df["day_of_week"] = df["dt"].dt.day_name()

    issues_df = df[df["issue_category"].str.lower() != "none"].copy()
    if issues_df.empty:
        issues_df = df.copy()

    weeks = sorted(df["week"].unique().tolist())
    items = sorted(issues_df["item"].unique().tolist())
    categories = sorted(issues_df["issue_category"].unique().tolist())

    index = pd.MultiIndex.from_product([weeks, items, categories], names=["week", "item", "issue_category"])
    panel = pd.DataFrame(index=index).reset_index()

    agg = issues_df.groupby(["week", "item", "issue_category"]).agg(
        complaints_count=("feedback_id", "count"),
        complaint_channel_count=("channel", lambda x: (x == "complaint").sum()),
        avg_rating=("rating", "mean"),
        is_exam_week=("is_exam_week", lambda x: int(x.max()) if "is_exam_week" in issues_df.columns else 0)
    ).reset_index()

    panel = pd.merge(panel, agg, on=["week", "item", "issue_category"], how="left")
    panel["complaints_count"] = panel["complaints_count"].fillna(0).astype(int)
    panel["complaint_channel_count"] = panel["complaint_channel_count"].fillna(0).astype(int)
    panel["avg_rating"] = panel["avg_rating"].fillna(3.5)
    panel["is_exam_week"] = panel["is_exam_week"].fillna(0).astype(int)

    panel = panel.sort_values(["item", "issue_category", "week"]).reset_index(drop=True)

    grouped = panel.groupby(["item", "issue_category"])
    panel["lag_1"] = grouped["complaints_count"].shift(1).fillna(0)
    panel["lag_2"] = grouped["complaints_count"].shift(2).fillna(0)
    panel["lag_4"] = grouped["complaints_count"].shift(4).fillna(0)
    panel["rolling_4w_mean"] = grouped["complaints_count"].transform(
        lambda s: s.shift(1).rolling(4, min_periods=1).mean()
    ).fillna(0)
    panel["rolling_avg_rating"] = grouped["avg_rating"].transform(
        lambda s: s.shift(1).rolling(4, min_periods=1).mean()
    ).fillna(3.5)

    def calc_weeks_since(s: pd.Series) -> pd.Series:
        result = []
        counter = 99
        for val in s:
            result.append(counter)
            if val > 0:
                counter = 1
            else:
                counter += 1
        return pd.Series(result, index=s.index)

    panel["weeks_since_last_issue"] = grouped["complaints_count"].transform(calc_weeks_since)
    panel["target_next_week"] = grouped["complaints_count"].shift(-1)
    panel["target_binary"] = (panel["target_next_week"] >= 1).astype(int)

    return panel


def train_recurrence_model(
    panel_df: pd.DataFrame,
    split_week: Optional[int] = None
) -> Tuple[Any, Dict[str, float], List[str], pd.DataFrame]:
    feature_cols = [
        "lag_1", "lag_2", "lag_4", "rolling_4w_mean",
        "rolling_avg_rating", "weeks_since_last_issue", "is_exam_week"
    ]

    valid_data = panel_df.dropna(subset=["target_next_week"]).copy()
    total_weeks = sorted(valid_data["week"].unique().tolist())
    if split_week is None:
        cutoff_idx = max(1, int(len(total_weeks) * 0.75))
        split_week = total_weeks[cutoff_idx]

    train_data = valid_data[valid_data["week"] < split_week]
    test_data = valid_data[valid_data["week"] >= split_week]

    if train_data.empty or test_data.empty:
        train_data = valid_data.iloc[:int(len(valid_data)*0.7)]
        test_data = valid_data.iloc[int(len(valid_data)*0.7):]

    X_train = train_data[feature_cols]
    y_train = train_data["target_binary"]
    X_test = test_data[feature_cols]
    y_test = test_data["target_binary"]

    model = None
    if HAS_LIGHTGBM:
        try:
            model = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=4,
                random_state=42,
                verbose=-1
            )
            model.fit(X_train, y_train)
        except Exception:
            model = None

    if model is None:
        model = HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.05,
            max_depth=4,
            random_state=42
        )
        model.fit(X_train, y_train)

    preds_proba = model.predict_proba(X_test)[:, 1]
    preds_binary = (preds_proba >= 0.40).astype(int)

    precision = float(precision_score(y_test, preds_binary, zero_division=0))
    recall = float(recall_score(y_test, preds_binary, zero_division=0))
    try:
        auc = float(roc_auc_score(y_test, preds_proba))
    except Exception:
        auc = 0.50

    metrics = {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "auc": round(auc, 3),
        "train_samples": len(train_data),
        "test_samples": len(test_data),
        "split_week": split_week
    }

    test_results = test_data[["week", "item", "issue_category", "target_binary"]].copy()
    test_results["pred_probability"] = preds_proba
    test_results["predicted_recurrence"] = preds_binary

    return model, metrics, feature_cols, test_results


def predict_next_week_risks(
    panel_df: pd.DataFrame,
    model: Any,
    feature_cols: List[str]
) -> pd.DataFrame:
    max_week = panel_df["week"].max()
    latest_rows = panel_df[panel_df["week"] == max_week].copy()

    if latest_rows.empty:
        return pd.DataFrame()

    X_latest = latest_rows[feature_cols].copy()
    probs = model.predict_proba(X_latest)[:, 1]
    latest_rows["recurrence_prob"] = np.round(probs, 3)

    def get_tier(prob):
        if prob >= 0.70:
            return "Critical"
        elif prob >= 0.45:
            return "High"
        elif prob >= 0.25:
            return "Medium"
        else:
            return "Low"

    latest_rows["risk_tier"] = latest_rows["recurrence_prob"].apply(get_tier)

    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        top_feature_idx = np.argmax(importances)
        top_feat_name = feature_cols[top_feature_idx]
    else:
        top_feat_name = "lag_1"

    latest_rows["top_factor"] = top_feat_name

    output_cols = [
        "item", "issue_category", "recurrence_prob", "risk_tier",
        "lag_1", "lag_2", "rolling_4w_mean", "weeks_since_last_issue", "top_factor"
    ]
    return latest_rows[output_cols].sort_values("recurrence_prob", ascending=False).reset_index(drop=True)


def detect_rating_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if "date" in df.columns:
        df = df.copy()
        df["dt"] = pd.to_datetime(df["date"])
        if "week" not in df.columns:
            min_date = df["dt"].min()
            df["week"] = ((df["dt"] - min_date).dt.days // 7) + 1

    max_week = df["week"].max()
    anomalies = []

    for item, item_df in df.groupby("item"):
        if len(item_df) < 15:
            continue

        baseline_df = item_df[item_df["week"] <= max_week - 2]
        recent_df = item_df[item_df["week"] > max_week - 2]

        if baseline_df.empty or recent_df.empty:
            continue

        base_mean = baseline_df["rating"].mean()
        base_std = baseline_df["rating"].std()
        recent_mean = recent_df["rating"].mean()

        if pd.isna(base_std) or base_std < 0.1:
            base_std = 0.5

        drop = base_mean - recent_mean
        z_score = drop / base_std

        if z_score > 1.0 and drop > 0.4:
            anomalies.append({
                "item": item,
                "baseline_rating": round(base_mean, 2),
                "recent_rating": round(recent_mean, 2),
                "drop": round(drop, 2),
                "std_drop": round(z_score, 2),
                "message": f"Rating plunged from {base_mean:.1f}★ to {recent_mean:.1f}★ (-{z_score:.1f}σ drop)"
            })

    return sorted(anomalies, key=lambda a: a["drop"], reverse=True)
