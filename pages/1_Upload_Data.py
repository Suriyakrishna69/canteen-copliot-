"""
Canteen Copilot - Page 1: Upload Data & Source Configuration.
"""

import os
import streamlit as st
import pandas as pd
from src.connectors import SyntheticSource, CSVSource, ZomatoKaggleSource, GoogleReviewsSource, ZomatoAPISource, SwiggySource
from src.nlp import enrich_feedback_dataframe
from src.predict import build_weekly_panel, train_recurrence_model, predict_next_week_risks
from src.prioritize import calculate_priorities

st.set_page_config(page_title="Upload Data - Canteen Copilot", page_icon="📥", layout="wide")

with st.sidebar:
    st.info("ℹ️ **Demo uses synthetic data; Zomato dataset used for model grounding**")

st.title("📥 Feedback Data Ingestion & Connectors")
st.markdown("Select or upload customer feedback data from various sources to ingest into the Copilot intelligence pipeline.")

source_type = st.radio(
    "Select Feedback Source",
    options=[
        "Synthetic Demo Generator (Planted Patterns)",
        "Custom CSV Upload",
        "Kaggle Zomato Dataset (Grounding)",
        "Google Reviews (Partner API)",
        "Zomato Enterprise API",
        "Swiggy Business API"
    ],
    horizontal=False
)

st.markdown("---")

if source_type == "Synthetic Demo Generator (Planted Patterns)":
    st.markdown("#### 🧪 Synthetic Dataset Settings")
    st.write("Generates 12 weeks of realistic campus dining feedback containing engineered real-world patterns.")

    col1, col2, col3 = st.columns(3)
    with col1:
        num_rows = st.slider("Number of Feedback Records", min_value=1000, max_value=5000, value=3000, step=500)
    with col2:
        weeks = st.slider("Time Span (Weeks)", min_value=4, max_value=24, value=12, step=1)
    with col3:
        seed = st.number_input("Random Seed (for reproducibility)", value=42, min_value=1, max_value=9999)

    if st.button("Generate & Ingest Dataset", type="primary"):
        with st.spinner("Generating synthetic data and running NLP analysis..."):
            source = SyntheticSource(num_rows=num_rows, weeks=weeks, force_regenerate=True)
            raw_df = source.load()
            enriched_df = enrich_feedback_dataframe(raw_df)
            panel_df = build_weekly_panel(enriched_df)
            model, metrics, feature_cols, _ = train_recurrence_model(panel_df)
            predictions_df = predict_next_week_risks(panel_df, model, feature_cols)
            priorities_df = calculate_priorities(enriched_df, predictions_df)

            st.session_state["copilot_data"] = {
                "raw_df": raw_df,
                "enriched_df": enriched_df,
                "panel_df": panel_df,
                "model": model,
                "metrics": metrics,
                "feature_cols": feature_cols,
                "predictions_df": predictions_df,
                "priorities_df": priorities_df
            }
            st.success(f"Successfully generated and ingested {len(raw_df)} feedback rows!")
            st.rerun()

elif source_type == "Custom CSV Upload":
    st.markdown("#### 📂 Upload Custom CSV")
    uploaded_file = st.file_uploader("Upload CSV file with canteen reviews", type=["csv"])

    if uploaded_file is not None:
        raw_preview = pd.read_csv(uploaded_file)
        st.write("Uploaded File Preview (first 5 rows):")
        st.dataframe(raw_preview.head(5), use_container_width=True)

        st.markdown("#### 🗺️ Column Mapping")
        st.write("Map the uploaded columns to Canteen Copilot's standard schema:")

        cols = ["-- Select Column --"] + list(raw_preview.columns)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            item_col = st.selectbox("Item / Dish Column", cols, index=1 if len(cols) > 1 else 0)
            rating_col = st.selectbox("Rating Column (1-5)", cols, index=2 if len(cols) > 2 else 0)
        with c2:
            comment_col = st.selectbox("Review / Comment Column", cols, index=3 if len(cols) > 3 else 0)
            date_col = st.selectbox("Date / Timestamp Column", cols, index=0)
        with c3:
            channel_col = st.selectbox("Channel Column (form/complaint)", cols, index=0)
            meal_col = st.selectbox("Meal Type Column", cols, index=0)
        with c4:
            cat_col = st.selectbox("Issue Category Column", cols, index=0)

        if st.button("Run Full Analysis Pipeline", type="primary"):
            mapping = {}
            if item_col != "-- Select Column --": mapping["item"] = item_col
            if rating_col != "-- Select Column --": mapping["rating"] = rating_col
            if comment_col != "-- Select Column --": mapping["comment"] = comment_col
            if date_col != "-- Select Column --": mapping["date"] = date_col
            if channel_col != "-- Select Column --": mapping["channel"] = channel_col
            if meal_col != "-- Select Column --": mapping["meal_type"] = meal_col
            if cat_col != "-- Select Column --": mapping["issue_category"] = cat_col

            uploaded_file.seek(0)
            source = CSVSource(uploaded_file, column_mapping=mapping)
            raw_df = source.load()

            with st.spinner("Processing NLP tags, training recurrence model, and calculating priorities..."):
                enriched_df = enrich_feedback_dataframe(raw_df)
                panel_df = build_weekly_panel(enriched_df)
                model, metrics, feature_cols, _ = train_recurrence_model(panel_df)
                predictions_df = predict_next_week_risks(panel_df, model, feature_cols)
                priorities_df = calculate_priorities(enriched_df, predictions_df)

                st.session_state["copilot_data"] = {
                    "raw_df": raw_df,
                    "enriched_df": enriched_df,
                    "panel_df": panel_df,
                    "model": model,
                    "metrics": metrics,
                    "feature_cols": feature_cols,
                    "predictions_df": predictions_df,
                    "priorities_df": priorities_df
                }
                st.success("Analysis complete!")
                st.rerun()

elif source_type == "Kaggle Zomato Dataset (Grounding)":
    st.markdown("#### 🍽️ Kaggle Zomato Dataset Ingestion")
    st.write("Reads real-world Indian restaurant reviews (`data/zomato.csv`) to stress-test NLP parsing on genuine user phrasing.")
    zomato_path = "data/zomato.csv"
    if not os.path.exists(zomato_path):
        st.warning(f"File '{zomato_path}' not found on disk. Place zomato.csv in data/ or use the Synthetic Generator.")
    else:
        max_rows = st.slider("Rows to load", 100, 2000, 500)
        if st.button("Load Zomato Data & Analyze", type="primary"):
            with st.spinner("Parsing Zomato reviews..."):
                source = ZomatoKaggleSource(file_path=zomato_path, max_rows=max_rows)
                raw_df = source.load()
                enriched_df = enrich_feedback_dataframe(raw_df)
                panel_df = build_weekly_panel(enriched_df)
                model, metrics, feature_cols, _ = train_recurrence_model(panel_df)
                predictions_df = predict_next_week_risks(panel_df, model, feature_cols)
                priorities_df = calculate_priorities(enriched_df, predictions_df)

                st.session_state["copilot_data"] = {
                    "raw_df": raw_df,
                    "enriched_df": enriched_df,
                    "panel_df": panel_df,
                    "model": model,
                    "metrics": metrics,
                    "feature_cols": feature_cols,
                    "predictions_df": predictions_df,
                    "priorities_df": priorities_df
                }
                st.success("Zomato data ingested!")
                st.rerun()

else:
    st.markdown("#### 🔒 Partner API Integration")
    st.info("🚧 **Status: Coming Soon**")
    st.error("Requires official partner API access & OAuth verification. Web scraping is strictly prohibited.")
    st.write("To request enterprise partner API access for Google Reviews, Zomato API, or Swiggy Partner Portal, contact your campus food vendor management team.")

if "copilot_data" in st.session_state:
    st.markdown("---")
    st.markdown("### 📋 Active Ingested Dataset Summary")
    active_df = st.session_state["copilot_data"]["enriched_df"]
    st.write(f"**Loaded Records:** {len(active_df):,} | **Unique Dishes:** {active_df['item'].nunique()} | **Date Range:** {active_df['date'].min()[:10]} to {active_df['date'].max()[:10]}")
    st.dataframe(active_df.head(10), use_container_width=True)
