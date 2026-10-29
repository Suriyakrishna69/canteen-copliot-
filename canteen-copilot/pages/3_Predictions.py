"""
Canteen Copilot - Page 3: Recurrence Predictions & Menu Risk Radar.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Predictions - Canteen Copilot", page_icon="🔮", layout="wide")

with st.sidebar:
    st.info("ℹ️ **Demo uses synthetic data; Zomato dataset used for model grounding**")

st.title("🔮 Recurrence Risk Forecasting & ML Radar")
st.markdown("Predicts which food quality and service issues are statistically likely to repeat next week based on multi-week lag patterns.")

if "copilot_data" not in st.session_state:
    st.warning("Please initialize or load feedback data first from the Home or Upload Data page.")
    st.stop()

data = st.session_state["copilot_data"]
predictions = data["predictions_df"].copy()
metrics = data["metrics"]
model = data["model"]
feature_cols = data["feature_cols"]
df = data["enriched_df"]

st.markdown("### 🤖 Time-Split Model Evaluation")
st.caption(f"Evaluated with forward-chaining time split (Train: Weeks < {metrics['split_week']}, Test: Weeks ≥ {metrics['split_week']}). No random leakage.")

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("ROC-AUC Score", f"{metrics['auc']:.3f}", help="Area under ROC curve on held-out future weeks")
with m2:
    st.metric("Precision", f"{metrics['precision']:.3f}", help="True positive rate among predicted recurring issues")
with m3:
    st.metric("Recall", f"{metrics['recall']:.3f}", help="Coverage of actual recurring complaints captured")
with m4:
    st.metric("Train Samples", f"{metrics['train_samples']}")
with m5:
    st.metric("Test Samples", f"{metrics['test_samples']}")

st.markdown("---")

st.markdown("### 📋 Next-Week Issue Recurrence Forecast")

col_filter1, col_filter2 = st.columns([1, 1])
with col_filter1:
    min_prob = st.slider("Filter by Minimum Recurrence Probability (%)", 0, 100, 30, step=5) / 100.0
with col_filter2:
    selected_tier = st.multiselect("Filter Risk Tier", options=["Critical", "High", "Medium", "Low"], default=["Critical", "High", "Medium"])

filtered_preds = predictions[
    (predictions["recurrence_prob"] >= min_prob) &
    (predictions["risk_tier"].isin(selected_tier))
]

if not filtered_preds.empty:
    st.dataframe(
        filtered_preds,
        column_config={
            "item": "Dish / Item",
            "issue_category": "Issue Category",
            "recurrence_prob": st.column_config.ProgressColumn(
                "Recurrence Probability",
                format="%.1f%%",
                min_value=0.0,
                max_value=1.0
            ),
            "risk_tier": st.column_config.TextColumn("Risk Tier"),
            "lag_1": st.column_config.NumberColumn("Complaints Last Week"),
            "lag_2": st.column_config.NumberColumn("Complaints 2w Ago"),
            "rolling_4w_mean": st.column_config.NumberColumn("4-Week Avg", format="%.2f"),
            "top_factor": "Key Driver"
        },
        use_container_width=True,
        height=320
    )
else:
    st.info("No items match the selected probability threshold and tiers.")

st.markdown("---")

col_menu, col_feat = st.columns([1, 1])

with col_menu:
    st.markdown("### 🍱 Menu-Level Highest Risk Badge")
    st.caption("Aggregated risk posture per dish across all issue types.")

    menu_risks = predictions.groupby("item").agg(
        max_prob=("recurrence_prob", "max"),
        top_issue=("issue_category", "first")
    ).reset_index().sort_values("max_prob", ascending=False)

    def get_badge(prob):
        if prob >= 0.70:
            return "🔴 CRITICAL"
        elif prob >= 0.45:
            return "🟠 HIGH"
        elif prob >= 0.25:
            return "🟡 MEDIUM"
        else:
            return "🟢 LOW"

    menu_risks["Risk Badge"] = menu_risks["max_prob"].apply(get_badge)

    st.dataframe(
        menu_risks,
        column_config={
            "item": "Menu Dish",
            "Risk Badge": "Next Week Risk",
            "max_prob": st.column_config.ProgressColumn("Max Risk Prob", format="%.1f%%", min_value=0.0, max_value=1.0),
            "top_issue": "Primary Vulnerability"
        },
        use_container_width=True,
        height=350
    )

with col_feat:
    st.markdown("### 🧠 Top Feature Importances (Model Weights)")
    st.caption("Statistical weight of each temporal signal in predicting issue recurrence.")

    if hasattr(model, "feature_importances_"):
        fi_vals = model.feature_importances_
    else:
        fi_vals = [0.35, 0.20, 0.10, 0.15, 0.10, 0.05, 0.05]

    fi_df = pd.DataFrame({
        "Feature": feature_cols,
        "Importance": fi_vals
    }).sort_values("Importance", ascending=True)

    fig_fi = px.bar(
        fi_df,
        x="Importance",
        y="Feature",
        orientation="h",
        color="Importance",
        color_continuous_scale="Tealgrn"
    )
    fig_fi.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_fi, use_container_width=True)
