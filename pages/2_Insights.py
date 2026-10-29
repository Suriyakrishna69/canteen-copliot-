"""
Canteen Copilot - Page 2: Operational Insights & Anomaly Heatmaps.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.nlp import discover_topics

st.set_page_config(page_title="Insights - Canteen Copilot", page_icon="📈", layout="wide")

with st.sidebar:
    st.info("ℹ️ **Demo uses synthetic data; Zomato dataset used for model grounding**")

st.title("📈 Quality Insights & Trend Intelligence")
st.markdown("Diagnose customer sentiment trends, day-of-week complaint spikes, rating discrepancies, and emerging topics.")

if "copilot_data" not in st.session_state:
    st.warning("Please initialize or load feedback data first from the Home or Upload Data page.")
    st.stop()

data = st.session_state["copilot_data"]
df = data["enriched_df"].copy()
df["dt"] = pd.to_datetime(df["date"])

st.sidebar.markdown("### 🔍 Filter Controls")
meal_filter = st.sidebar.multiselect(
    "Meal Type",
    options=["breakfast", "lunch", "snacks", "dinner"],
    default=["breakfast", "lunch", "snacks", "dinner"]
)
channel_filter = st.sidebar.multiselect(
    "Channel",
    options=["form", "complaint"],
    default=["form", "complaint"]
)
all_items = sorted(df["item"].unique().tolist())
item_filter = st.sidebar.multiselect(
    "Filter Specific Items (Optional)",
    options=all_items,
    default=[]
)

filtered_df = df[
    (df["meal_type"].isin(meal_filter)) &
    (df["channel"].isin(channel_filter))
]
if item_filter:
    filtered_df = filtered_df[filtered_df["item"].isin(item_filter)]

if filtered_df.empty:
    st.error("No records match the selected filters. Please expand your filter selections.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Filtered Records", f"{len(filtered_df):,}")
with c2:
    st.metric("Average Rating", f"{filtered_df['rating'].mean():.2f} ★")
with c3:
    neg_ratio = (filtered_df["sentiment_label"] == "negative").mean() * 100
    st.metric("% Negative Sentiment", f"{neg_ratio:.1f}%")
with c4:
    top_issue = filtered_df[filtered_df["issue_category"] != "none"]["issue_category"].mode()
    st.metric("Most Frequent Issue", top_issue[0].capitalize() if not top_issue.empty else "None")

st.markdown("---")

st.markdown("### 📉 Sentiment Timeline & Mid-Semester Quality Shifts")
col_trend, col_dist = st.columns([2, 1])

with col_trend:
    weekly_item = filtered_df.groupby(["week", "item"]).agg(
        avg_rating=("rating", "mean"),
        count=("feedback_id", "count")
    ).reset_index()

    fig_trend = px.line(
        weekly_item,
        x="week",
        y="avg_rating",
        color="item",
        title="Weekly Average Rating per Dish (Hover for Details)",
        labels={"week": "Week Number", "avg_rating": "Average Rating (1-5)"},
        markers=True
    )
    fig_trend.add_vline(x=6.5, line_dash="dash", line_color="red", annotation_text="W6 Quality Shift", annotation_position="top left")
    fig_trend.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_trend, use_container_width=True)

with col_dist:
    st.markdown("#### 🚨 Detected Quality Anomalies")
    from src.predict import detect_rating_anomalies
    anomalies = detect_rating_anomalies(filtered_df)
    if anomalies:
        for anom in anomalies[:3]:
            st.error(f"**{anom['item']}**\n\n{anom['message']}")
    else:
        st.success("No critical rating plunge (>1σ) detected across recent weeks.")

st.markdown("---")

st.markdown("### 🗓️ Item vs. Day-of-Week Complaint Heatmap")
st.caption("Visualizes operational failure patterns (e.g. Friday Paneer freshness or Monday morning breakfast rushes).")

complaints_only = filtered_df[filtered_df["issue_category"] != "none"]
days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

pivot_data = complaints_only.pivot_table(
    index="item",
    columns="day_of_week",
    values="feedback_id",
    aggfunc="count",
    fill_value=0
)
present_days = [d for d in days_order if d in pivot_data.columns]
pivot_data = pivot_data[present_days]

fig_heat = px.imshow(
    pivot_data,
    labels=dict(x="Day of Week", y="Food Item", color="Complaints"),
    x=pivot_data.columns,
    y=pivot_data.index,
    color_continuous_scale="Reds",
    aspect="auto"
)
fig_heat.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("---")

col_topics, col_mismatches = st.columns([1, 1])

with col_topics:
    st.markdown("### 💡 Discovered Unsupervised Topics (NMF)")
    st.caption("Emerging student discussion themes extracted directly from raw text.")

    meal_choice = st.selectbox("Analyze Topics for Meal Type:", options=["All Meals"] + meal_filter)
    if meal_choice == "All Meals":
        text_pool = filtered_df["comment"].tolist()
    else:
        text_pool = filtered_df[filtered_df["meal_type"] == meal_choice]["comment"].tolist()

    discovered = discover_topics(text_pool, n_topics=4)
    if discovered:
        for t in discovered:
            with st.container():
                st.markdown(f"**Topic #{t['topic_id']}: {t['title']}** ({t['count']} mentions)")
                st.write(f"*Keywords:* `{'`, `'.join(t['keywords'])}`")
                st.progress(min(1.0, t['count'] / max(1, len(text_pool))))
    else:
        st.info("Not enough text sample size to extract distinct semantic clusters.")

with col_mismatches:
    st.markdown("### ⚠️ Rating-Text Mismatches")
    st.caption("Identifies sarcastic reviews, mis-clicks, or contradictory ratings (e.g. 5★ rating with negative complaints).")

    mismatch_df = filtered_df[filtered_df["is_mismatch"] == True][["rating", "sentiment_score", "item", "comment"]]
    if not mismatch_df.empty:
        st.dataframe(
            mismatch_df.head(8),
            column_config={
                "rating": st.column_config.NumberColumn("Given Stars", format="%d ★"),
                "sentiment_score": st.column_config.NumberColumn("NLP Sentiment", format="%.2f"),
                "item": "Item",
                "comment": "Student Comment"
            },
            use_container_width=True,
            height=300
        )
    else:
        st.success("No rating-text contradictions identified in current filter window.")
