"""
Synthetic Data Generator for Canteen Copilot.

Generates realistic canteen feedback over 12 weeks with known planted patterns:
1. "Paneer Butter Masala" gets freshness complaints mostly on Fridays.
2. Monday breakfast has long wait_time complaints.
3. "Chicken Curry" taste ratings drop sharply after week 6.
4. "Dal Tadka" gets recurring "too salty" complaints, roughly weekly.
5. Rare but critical food_safety complaints (hair, insect) on random items.
6. Exam weeks (weeks 5 and 10) have higher complaint volume.
7. Complaints (channel='complaint') are more negative and severe than form entries.
8. ~10% noise with Hinglish/Tanglish phrases and ~3% rating-text mismatches.
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np

DEFAULT_SEED = 42

ITEMS_BY_MEAL = {
    "breakfast": ["Idli Sambar", "Masala Dosa", "Poha", "Upma", "Medu Vada", "Filter Coffee", "Masala Chai"],
    "lunch": ["Paneer Butter Masala", "Chicken Curry", "Dal Tadka", "Steamed Rice", "Chapati", "Veg Biryani", "Curd Rice"],
    "snacks": ["Samosa", "Vada Pav", "Masala Chai", "Filter Coffee", "Pakora", "Veg Sandwich"],
    "dinner": ["Paneer Butter Masala", "Chicken Curry", "Dal Tadka", "Jeera Rice", "Chapati", "Egg Curry", "Khichdi"]
}

ALL_ITEMS = sorted(list({item for sublist in ITEMS_BY_MEAL.values() for item in sublist}))

CATEGORIES = [
    "taste", "hygiene", "food_safety", "temperature",
    "portion", "wait_time", "staff_behavior", "freshness", "price", "none"
]

CATEGORY_SEVERITY = {
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

COMMENTS_MAP = {
    "freshness": {
        "positive": [
            "Paneer was extremely fresh and soft today!",
            "Vegetables tasted very fresh and crisp.",
            "Fresh batch served hot, loved it.",
            "Sabji bilkul fresh thi, maza aa gaya."
        ],
        "negative": [
            "Paneer tasted sour and rubbery, smells stale like yesterday's batch.",
            "Food smells stale and old, couldn't eat it.",
            "Paneer was totally stale and hard, not fresh at all.",
            "The gravy smelled weird and spoiled, definitely not fresh.",
            "Paneer smells stale ya, please check kitchen stock.",
            "Basi lag raha tha paneer, stale smell aa rahi thi."
        ]
    },
    "wait_time": {
        "positive": [
            "Quick service at the counter today.",
            "Tokens handled efficiently, food ready in 2 minutes.",
            "Very fast counter turnaround this morning."
        ],
        "negative": [
            "Waited over 25 minutes in line for breakfast token, completely unorganized!",
            "Too much crowd at counter, huge queue and waiting time.",
            "Tokens moving at snail pace, missed my morning lecture.",
            "Breakfast counter wait time is ridiculous on Monday morning.",
            "Bahut lamba queue tha, 30 min lag gaye token lene me.",
            "Counter staff was extremely slow, 20 mins just for dosa."
        ]
    },
    "taste": {
        "positive": [
            "Great flavor and perfect spices!",
            "Very tasty and authentic seasoning today.",
            "Delicious meal, loved the gravy.",
            "Swad bahut badhiya tha, bilkul homely taste."
        ],
        "negative": [
            "Dal is way too salty, couldn't finish even half the bowl.",
            "Curry was extremely bland and watery today, quality has dropped.",
            "Gravy tastes burnt and strange, totally off.",
            "Chicken curry gravy quality has degraded badly, oily and tasteless.",
            "Sambar bahut watery tha aur bilkul feeka tha.",
            "Extremely oily and bitter aftertaste in the curry."
        ]
    },
    "food_safety": {
        "positive": [],
        "negative": [
            "Found a long black hair inside my food! Completely unacceptable!",
            "There was a dead insect in the gravy bowl. Absolute biohazard!",
            "Found a small metal staple in the rice! Highly dangerous!",
            "Small caterpillar found crawling on lettuce leaf in plate.",
            "Disgusting! Cockroach leg found inside the sabji container."
        ]
    },
    "hygiene": {
        "positive": [
            "Plates and spoons were clean and sanitized.",
            "Very neat counter setup today.",
            "Hygiene standards have visibly improved."
        ],
        "negative": [
            "Plates have grease stains and smell like dirty dishwater.",
            "Server handling chapatis with bare unwashed hands.",
            "Flies buzzing around the open food trays, very unhygienic.",
            "Tables were greasy and leftover food left uncleaned for an hour.",
            "Serving spoons had dried curry stuck on them."
        ]
    },
    "temperature": {
        "positive": [
            "Served piping hot, perfect for the weather.",
            "Nice and warm food.",
            "Chai was steaming hot and refreshing."
        ],
        "negative": [
            "Food was stone cold when served, especially the rice and curry.",
            "Chai thanda tha, cold and disappointing.",
            "Sambar was lukewarm and congealed.",
            "Dosa was cold and soggy by the time I picked up the plate."
        ]
    },
    "portion": {
        "positive": [
            "Generous portion size, very filling.",
            "Good quantity for the price paid."
        ],
        "negative": [
            "Portion size has shrunk dramatically, barely three bites of paneer.",
            "Very small serving of curry, mostly gravy and no pieces.",
            "Rice portion was too little for a full lunch plate."
        ]
    },
    "staff_behavior": {
        "positive": [
            "Counter staff was polite and helpful.",
            "Friendly canteen uncle served with a smile."
        ],
        "negative": [
            "Staff was rude and shouted when asked for extra sambar.",
            "Cashier was dismissive and threw change on the counter.",
            "Counter person was arrogant and ignored students."
        ]
    },
    "price": {
        "positive": [
            "Great student-friendly prices.",
            "Value for money canteen meals."
        ],
        "negative": [
            "Price increased by 15 rupees but quality became worse.",
            "Too expensive for such small canteen portions."
        ]
    },
    "none": {
        "positive": [
            "Decent canteen meal overall.",
            "Standard regular food, nothing to complain about.",
            "All good today, satisfied.",
            "Theek thaak tha, no complaints."
        ],
        "negative": [
            "Average experience today.",
            "Expected better food today."
        ]
    }
}


def generate_synthetic_feedback(
    num_rows: int = 3000,
    weeks: int = 12,
    start_date: Optional[datetime] = None,
    seed: int = DEFAULT_SEED,
    zomato_csv_path: Optional[str] = "data/zomato.csv"
) -> pd.DataFrame:
    """Generate synthetic canteen feedback with planted patterns."""
    random.seed(seed)
    np.random.seed(seed)

    if start_date is None:
        start_date = datetime(2026, 8, 3, 8, 0, 0)

    records: List[Dict[str, Any]] = []

    zomato_phrases: List[str] = []
    if zomato_csv_path and os.path.exists(zomato_csv_path):
        try:
            zdf = pd.read_csv(zomato_csv_path, nrows=1000)
            if "reviews_list" in zdf.columns:
                reviews = zdf["reviews_list"].dropna().sample(min(200, len(zdf)), random_state=seed)
                for rev in reviews:
                    if isinstance(rev, str) and len(rev) > 20:
                        clean_rev = rev.replace("Rated 1.0", "").replace("Rated 5.0", "").strip("[](),'\"")
                        if len(clean_rev) > 15:
                            zomato_phrases.append(clean_rev[:140])
        except Exception:
            pass

    total_days = weeks * 7

    for i in range(1, num_rows + 1):
        feedback_id = f"FB-{i:05d}"
        day_offset = random.randint(0, total_days - 1)
        current_date = start_date + timedelta(days=day_offset)
        week_num = (day_offset // 7) + 1
        day_of_week = current_date.strftime("%A")

        is_exam_week = week_num in [5, 10]

        meal_type = random.choices(
            ["breakfast", "lunch", "snacks", "dinner"],
            weights=[0.25, 0.40, 0.15, 0.20]
        )[0]

        complaint_prob = 0.35 if is_exam_week else 0.22
        channel = "complaint" if random.random() < complaint_prob else "form"
        item = random.choice(ITEMS_BY_MEAL[meal_type])

        issue_category = random.choices(
            CATEGORIES,
            weights=[0.18, 0.10, 0.015, 0.12, 0.10, 0.14, 0.08, 0.10, 0.06, 0.105]
        )[0]
        rating = random.choices([1, 2, 3, 4, 5], weights=[0.2, 0.25, 0.25, 0.18, 0.12])[0]
        comment = ""

        # Pattern 1: Paneer Friday Freshness
        if item == "Paneer Butter Masala" and day_of_week == "Friday" and random.random() < 0.70:
            issue_category = "freshness"
            rating = random.choice([1, 2])
            comment = random.choice(COMMENTS_MAP["freshness"]["negative"])
            channel = random.choices(["complaint", "form"], weights=[0.6, 0.4])[0]

        # Pattern 2: Monday Breakfast Wait Time
        elif meal_type == "breakfast" and day_of_week == "Monday" and random.random() < 0.65:
            issue_category = "wait_time"
            rating = random.choice([1, 2])
            comment = random.choice(COMMENTS_MAP["wait_time"]["negative"])
            channel = "complaint" if random.random() < 0.7 else "form"

        # Pattern 3: Chicken Curry Quality Drop After Week 6
        elif item == "Chicken Curry":
            if week_num <= 6:
                rating = random.choices([4, 5], weights=[0.4, 0.6])[0]
                issue_category = "none"
                comment = random.choice([
                    "Chicken Curry was delicious and flavorful today!",
                    "Loved the tender chicken curry with rice, very rich gravy.",
                    "Excellent spices in the chicken curry today."
                ])
                channel = "form"
            else:
                issue_category = "taste"
                rating = random.choices([1, 2], weights=[0.7, 0.3])[0]
                comment = random.choice([
                    "Chicken curry gravy has degraded badly after week 6, too oily and bland.",
                    "Quality of chicken curry has taken a nosedive recently, tough meat and watery sauce.",
                    "Chicken curry tastes awful compared to last month, spices are completely off.",
                    "Curry was extremely bland and watery today, quality has dropped."
                ])
                channel = "complaint" if random.random() < 0.65 else "form"

        # Pattern 4: Dal Tadka Recurring Salt Complaints
        elif item == "Dal Tadka" and random.random() < 0.45:
            issue_category = "taste"
            rating = random.choice([1, 2])
            comment = random.choice([
                "Dal Tadka is way too salty again! Please control salt in the kitchen.",
                "Too much namak in dal tadka, impossible to eat without plain rice.",
                "Dal was overly salty today, recurring problem every single week.",
                "Dal is way too salty, couldn't finish even half the bowl."
            ])

        # Pattern 5: Rare Food Safety Complaints (~0.8%)
        elif random.random() < 0.008:
            issue_category = "food_safety"
            rating = 1
            comment = random.choice(COMMENTS_MAP["food_safety"]["negative"])
            channel = "complaint"

        if not comment:
            is_positive = rating >= 4
            pool = COMMENTS_MAP.get(issue_category, COMMENTS_MAP["none"])
            if is_positive and pool["positive"]:
                comment = random.choice(pool["positive"])
            elif not is_positive and pool["negative"]:
                comment = random.choice(pool["negative"])
            else:
                comment = f"{item} was {'good' if is_positive else 'average'} today."

        if channel == "complaint" and rating > 3:
            rating = random.choice([1, 2])
            if issue_category == "none":
                issue_category = random.choice(["taste", "wait_time", "hygiene", "portion"])
            pool = COMMENTS_MAP.get(issue_category, COMMENTS_MAP["taste"])
            if pool["negative"]:
                comment = random.choice(pool["negative"])

        # Hinglish noise ~10%
        if random.random() < 0.10:
            hinglish_fillers = [
                " Sambar bahut watery tha.",
                " Yaar service thoda slow tha.",
                " Biryani mast thi vaise.",
                " Chai bilkul thanda ho gaya tha.",
                " Ekdum bakwas experience."
            ]
            comment = comment.rstrip(".") + random.choice(hinglish_fillers)

        # Rating-text mismatch ~3%
        is_mismatch = False
        if random.random() < 0.03:
            is_mismatch = True
            if rating <= 2:
                rating = 5
            else:
                rating = 1

        hour = {
            "breakfast": random.randint(7, 10),
            "lunch": random.randint(12, 14),
            "snacks": random.randint(16, 18),
            "dinner": random.randint(19, 22)
        }[meal_type]
        minute = random.randint(0, 59)
        final_datetime = current_date.replace(hour=hour, minute=minute)

        records.append({
            "feedback_id": feedback_id,
            "date": final_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "meal_type": meal_type,
            "item": item,
            "rating": rating,
            "comment": comment,
            "channel": channel,
            "issue_category": issue_category,
            "week": week_num,
            "day_of_week": day_of_week,
            "is_exam_week": int(is_exam_week),
            "is_mismatch_injected": int(is_mismatch)
        })

    df = pd.DataFrame(records)
    return df


def save_to_storage(df: pd.DataFrame, csv_path: str = "data/synthetic_feedback.csv", db_path: str = "data/canteen.db") -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    df.to_csv(csv_path, index=False)
    conn = sqlite3.connect(db_path)
    df.to_sql("feedback", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    df = generate_synthetic_feedback(num_rows=3000, weeks=12)
    save_to_storage(df)
    print(f"Generated {len(df)} synthetic feedback rows.")
