"""
Prioritization Engine for Canteen Copilot.
"""

from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

EFFORT_MAP = {
    "taste": {"effort_name": "Low", "effort_val": 1.0, "reason": "Recipe adjustment / salt calibration"},
    "temperature": {"effort_name": "Low", "effort_val": 1.1, "reason": "Bain-marie / heating lamp maintenance"},
    "portion": {"effort_name": "Low", "effort_val": 1.2, "reason": "Standardized ladle portioning"},
    "freshness": {"effort_name": "Medium", "effort_val": 1.8, "reason": "Procurement / stock rotation schedule"},
    "wait_time": {"effort_name": "Medium", "effort_val": 2.0, "reason": "Counter token workflow & cashier speed"},
    "staff_behavior": {"effort_name": "Medium", "effort_val": 1.8, "reason": "Staff customer service briefing"},
    "hygiene": {"effort_name": "High", "effort_val": 2.5, "reason": "Deep sanitation protocol & dishwashing upgrade"},
    "food_safety": {"effort_name": "High", "effort_val": 2.8, "reason": "Urgent kitchen audit & supplier inspection"},
    "price": {"effort_name": "High", "effort_val": 3.0, "reason": "Menu pricing committee review"},
    "none": {"effort_name": "Low", "effort_val": 1.0, "reason": "No action needed"}
}

SEVERITY_WEIGHTS = {
    "food_safety": 5,
    "hygiene": 4,
    "freshness": 3,
    "temperature": 2,
    "taste": 2,
    "wait_time": 2,
    "portion": 1,
    "staff_behavior": 1,
    "price": 1,
    "none": 0
}


def calculate_priorities(
    feedback_df: pd.DataFrame,
    predictions_df: Optional[pd.DataFrame] = None,
    lookback_days: int = 14
) -> pd.DataFrame:
    df = feedback_df.copy()
    issues_df = df[df["issue_category"].str.lower() != "none"].copy()
    if issues_df.empty:
        return pd.DataFrame()

    if "date" in issues_df.columns:
        issues_df["dt"] = pd.to_datetime(issues_df["date"])
        max_date = issues_df["dt"].max()
        cutoff_date = max_date - pd.Timedelta(days=lookback_days)
        recent_df = issues_df[issues_df["dt"] >= cutoff_date]
        if recent_df.empty:
            recent_df = issues_df
    else:
        recent_df = issues_df

    recent_df["channel_weight"] = recent_df["channel"].apply(lambda c: 2.0 if str(c).lower() == "complaint" else 1.0)

    agg = recent_df.groupby(["item", "issue_category"]).agg(
        raw_count=("feedback_id", "count"),
        weighted_frequency=("channel_weight", "sum"),
        reach=("feedback_id", "nunique"),
        avg_rating=("rating", "mean"),
        sample_comments=("comment", lambda x: [c for c in x if isinstance(c, str) and len(c.strip()) > 5][:3])
    ).reset_index()

    if predictions_df is not None and not predictions_df.empty:
        merged = pd.merge(
            agg,
            predictions_df[["item", "issue_category", "recurrence_prob"]],
            on=["item", "issue_category"],
            how="left"
        )
        merged["recurrence_prob"] = merged["recurrence_prob"].fillna(0.35)
    else:
        merged = agg.copy()
        merged["recurrence_prob"] = 0.50

    def min_max_norm(series: pd.Series, floor: float = 0.1) -> pd.Series:
        s_min, s_max = series.min(), series.max()
        if s_max == s_min:
            return pd.Series(1.0, index=series.index)
        return floor + (1.0 - floor) * ((series - s_min) / (s_max - s_min))

    merged["freq_norm"] = min_max_norm(merged["weighted_frequency"])
    merged["reach_norm"] = min_max_norm(merged["reach"])
    merged["severity_val"] = merged["issue_category"].map(lambda c: SEVERITY_WEIGHTS.get(c, 1))
    merged["severity_norm"] = merged["severity_val"] / 5.0

    merged["effort_val"] = merged["issue_category"].map(lambda c: EFFORT_MAP.get(c, {"effort_val": 1.5})["effort_val"])
    merged["effort_name"] = merged["issue_category"].map(lambda c: EFFORT_MAP.get(c, {"effort_name": "Medium"})["effort_name"])

    raw_scores = (
        merged["freq_norm"] *
        merged["severity_norm"] *
        merged["recurrence_prob"] *
        merged["reach_norm"]
    ) / merged["effort_val"]

    max_raw = raw_scores.max() if raw_scores.max() > 0 else 1.0
    merged["score"] = np.round((raw_scores / max_raw) * 85.0 + 10.0, 1)

    # HARD RULE: food_safety is forced to top tier CRITICAL
    is_food_safety = merged["issue_category"] == "food_safety"
    merged.loc[is_food_safety, "score"] = 99.0

    def assign_tier(row):
        if row["issue_category"] == "food_safety":
            return "Critical"
        s = row["score"]
        if s >= 70:
            return "High"
        elif s >= 45:
            return "Medium"
        else:
            return "Low"

    merged["tier"] = merged.apply(assign_tier, axis=1)

    def build_why_sentence(row):
        item = row["item"]
        cat = row["issue_category"]
        prob = int(row["recurrence_prob"] * 100)
        cnt = row["raw_count"]
        effort = row["effort_name"]

        if cat == "food_safety":
            return f"CRITICAL: Biohazard/contamination reported on {item}. Hard rule mandates immediate inspection."
        elif cat == "freshness":
            return f"High freshness complaints on {item} ({cnt} in past 2w) with {prob}% recurrence risk; requires vendor/stock check."
        elif cat == "wait_time":
            return f"Recurring bottleneck on {item} affecting {row['reach']} students ({prob}% risk); {effort} effort token fix."
        elif cat == "taste":
            return f"Consistent seasoning/taste complaints on {item} with {prob}% recurrence; {effort} effort recipe calibration."
        elif cat == "hygiene":
            return f"Sanitation flags on {item} counter ({cnt} complaints); high severity hygiene intervention needed."
        else:
            return f"{cnt} recent {cat} issues on {item} with {prob}% recurrence risk; estimated {effort} effort."

    merged["why_ranked"] = merged.apply(build_why_sentence, axis=1)

    merged["is_critical"] = (merged["issue_category"] == "food_safety").astype(int)
    ranked = merged.sort_values(by=["is_critical", "score", "weighted_frequency"], ascending=[False, False, False]).reset_index(drop=True)

    output_cols = [
        "item", "issue_category", "tier", "score", "raw_count", "weighted_frequency",
        "recurrence_prob", "effort_name", "why_ranked", "sample_comments"
    ]
    return ranked[output_cols]
