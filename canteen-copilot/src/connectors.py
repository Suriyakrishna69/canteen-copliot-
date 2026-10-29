"""
Connector layer for Canteen Copilot.
"""

from abc import ABC, abstractmethod
import os
import re
import sqlite3
from typing import Dict, Any, Optional, List
import pandas as pd

STANDARD_COLUMNS = [
    "feedback_id",
    "date",
    "meal_type",
    "item",
    "rating",
    "comment",
    "channel",
    "issue_category"
]


class FeedbackSource(ABC):
    @abstractmethod
    def load(self) -> pd.DataFrame:
        pass


class SyntheticSource(FeedbackSource):
    def __init__(
        self,
        num_rows: int = 3000,
        weeks: int = 12,
        csv_path: str = "data/synthetic_feedback.csv",
        db_path: str = "data/canteen.db",
        force_regenerate: bool = False
    ):
        self.num_rows = num_rows
        self.weeks = weeks
        self.csv_path = csv_path
        self.db_path = db_path
        self.force_regenerate = force_regenerate

    def load(self) -> pd.DataFrame:
        if not self.force_regenerate and os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                df = pd.read_sql_query("SELECT * FROM feedback", conn)
                conn.close()
                if not df.empty and all(col in df.columns for col in STANDARD_COLUMNS):
                    return df[STANDARD_COLUMNS]
            except Exception:
                pass

        if not self.force_regenerate and os.path.exists(self.csv_path):
            try:
                df = pd.read_csv(self.csv_path)
                if not df.empty and all(col in df.columns for col in STANDARD_COLUMNS):
                    return df[STANDARD_COLUMNS]
            except Exception:
                pass

        from src.data_generator import generate_synthetic_feedback, save_to_storage
        df = generate_synthetic_feedback(num_rows=self.num_rows, weeks=self.weeks)
        save_to_storage(df, self.csv_path, self.db_path)
        return df[STANDARD_COLUMNS]


class CSVSource(FeedbackSource):
    def __init__(self, file_or_path: Any, column_mapping: Optional[Dict[str, str]] = None):
        self.file_or_path = file_or_path
        self.column_mapping = column_mapping or {}

    def load(self) -> pd.DataFrame:
        if isinstance(self.file_or_path, str):
            df = pd.read_csv(self.file_or_path)
        else:
            df = pd.read_csv(self.file_or_path)

        standard_df = pd.DataFrame()

        id_col = self.column_mapping.get("feedback_id")
        if id_col and id_col in df.columns:
            standard_df["feedback_id"] = df[id_col].astype(str)
        else:
            standard_df["feedback_id"] = [f"UPL-{i:05d}" for i in range(1, len(df) + 1)]

        item_col = self.column_mapping.get("item")
        if item_col and item_col in df.columns:
            standard_df["item"] = df[item_col].fillna("General Food").astype(str)
        else:
            standard_df["item"] = "General Food"

        rating_col = self.column_mapping.get("rating")
        if rating_col and rating_col in df.columns:
            def parse_rate(v):
                if pd.isna(v):
                    return 3
                s = str(v).split("/")[0].strip()
                try:
                    r = float(s)
                    return max(1, min(5, int(round(r))))
                except ValueError:
                    return 3
            standard_df["rating"] = df[rating_col].apply(parse_rate)
        else:
            standard_df["rating"] = 3

        comment_col = self.column_mapping.get("comment")
        if comment_col and comment_col in df.columns:
            standard_df["comment"] = df[comment_col].fillna("").astype(str)
        else:
            standard_df["comment"] = ""

        date_col = self.column_mapping.get("date")
        if date_col and date_col in df.columns:
            standard_df["date"] = pd.to_datetime(df[date_col], errors="coerce").fillna(pd.Timestamp.now()).dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            standard_df["date"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

        meal_col = self.column_mapping.get("meal_type")
        if meal_col and meal_col in df.columns:
            standard_df["meal_type"] = df[meal_col].fillna("lunch").astype(str).str.lower()
        else:
            standard_df["meal_type"] = "lunch"

        channel_col = self.column_mapping.get("channel")
        if channel_col and channel_col in df.columns:
            standard_df["channel"] = df[channel_col].fillna("form").astype(str).str.lower()
        else:
            standard_df["channel"] = "form"

        cat_col = self.column_mapping.get("issue_category")
        if cat_col and cat_col in df.columns:
            standard_df["issue_category"] = df[cat_col].fillna("none").astype(str).str.lower()
        else:
            standard_df["issue_category"] = "none"

        return standard_df[STANDARD_COLUMNS]


class ZomatoKaggleSource(FeedbackSource):
    def __init__(self, file_path: str = "data/zomato.csv", max_rows: int = 1500):
        self.file_path = file_path
        self.max_rows = max_rows

    def load(self) -> pd.DataFrame:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Zomato dataset not found at {self.file_path}.")

        df = pd.read_csv(self.file_path, nrows=self.max_rows * 2)
        records: List[Dict[str, Any]] = []
        count = 0

        name_col = "name" if "name" in df.columns else df.columns[0]
        rate_col = "rate" if "rate" in df.columns else None
        reviews_col = "reviews_list" if "reviews_list" in df.columns else None

        for idx, row in df.iterrows():
            if count >= self.max_rows:
                break

            restaurant_name = str(row[name_col]) if pd.notna(row[name_col]) else "Campus Cafe"

            raw_rate = str(row[rate_col]) if rate_col and pd.notna(row[rate_col]) else "3/5"
            rating = 3
            try:
                rate_val = float(raw_rate.split("/")[0].strip())
                rating = max(1, min(5, int(round(rate_val))))
            except Exception:
                rating = 3

            reviews_text = ""
            if reviews_col and pd.notna(row[reviews_col]):
                raw_rev = str(row[reviews_col])
                matches = re.findall(r"RATED\\n\s*(.*?)(?='\)|\"\)|, \('Rated)", raw_rev)
                if matches:
                    reviews_text = matches[0].strip()
                else:
                    reviews_text = raw_rev[:200]
            else:
                reviews_text = f"Review for {restaurant_name}"

            channel = "complaint" if rating <= 2 else "form"
            meal_type = "lunch" if rating % 2 == 0 else "dinner"

            records.append({
                "feedback_id": f"ZOM-{count+1:05d}",
                "date": (pd.Timestamp.now() - pd.Timedelta(days=count % 60)).strftime("%Y-%m-%d %H:%M:%S"),
                "meal_type": meal_type,
                "item": restaurant_name[:30],
                "rating": rating,
                "comment": reviews_text[:300],
                "channel": channel,
                "issue_category": "none"
            })
            count += 1

        return pd.DataFrame(records)[STANDARD_COLUMNS]


class GoogleReviewsSource(FeedbackSource):
    def load(self) -> pd.DataFrame:
        raise NotImplementedError("Requires official partner API access")


class ZomatoAPISource(FeedbackSource):
    def load(self) -> pd.DataFrame:
        raise NotImplementedError("Requires official partner API access")


class SwiggySource(FeedbackSource):
    def load(self) -> pd.DataFrame:
        raise NotImplementedError("Requires official partner API access")
