"""
Unit tests for Canteen Copilot Prioritization Engine.
"""

import pandas as pd
import pytest
from src.prioritize import calculate_priorities, SEVERITY_WEIGHTS, EFFORT_MAP


def test_food_safety_hard_rule_is_critical():
    data = [
        {"feedback_id": "1", "item": "Idli Sambar", "issue_category": "taste", "channel": "complaint", "rating": 1, "date": "2026-10-25 10:00:00", "comment": "Too salty"},
        {"feedback_id": "2", "item": "Idli Sambar", "issue_category": "taste", "channel": "complaint", "rating": 1, "date": "2026-10-25 10:00:00", "comment": "Too salty"},
        {"feedback_id": "3", "item": "Veg Biryani", "issue_category": "food_safety", "channel": "complaint", "rating": 1, "date": "2026-10-26 12:00:00", "comment": "Found insect in plate"},
        {"feedback_id": "4", "item": "Poha", "issue_category": "wait_time", "channel": "form", "rating": 2, "date": "2026-10-26 09:00:00", "comment": "Slow line"}
    ]
    df = pd.DataFrame(data)
    priorities = calculate_priorities(df)

    assert not priorities.empty
    top_issue = priorities.iloc[0]
    assert top_issue["issue_category"] == "food_safety"
    assert top_issue["tier"] == "Critical"
    assert top_issue["score"] >= 90.0
    assert "CRITICAL" in top_issue["why_ranked"]


def test_channel_weighting_impact():
    data_complaint = [
        {"feedback_id": f"c_{i}", "item": "Dal Tadka", "issue_category": "taste", "channel": "complaint", "rating": 2, "date": "2026-10-26 12:00:00", "comment": "Salty"}
        for i in range(5)
    ]
    data_form = [
        {"feedback_id": f"f_{i}", "item": "Chapati", "issue_category": "taste", "channel": "form", "rating": 2, "date": "2026-10-26 12:00:00", "comment": "Chewy"}
        for i in range(5)
    ]
    df = pd.DataFrame(data_complaint + data_form)
    priorities = calculate_priorities(df)

    dal = priorities[priorities["item"] == "Dal Tadka"].iloc[0]
    chapati = priorities[priorities["item"] == "Chapati"].iloc[0]

    assert dal["weighted_frequency"] == 10.0
    assert chapati["weighted_frequency"] == 5.0
    assert dal["score"] > chapati["score"]


def test_why_ranked_explanation_generated():
    data = [
        {"feedback_id": "1", "item": "Filter Coffee", "issue_category": "temperature", "channel": "form", "rating": 2, "date": "2026-10-25 10:00:00", "comment": "Cold"}
    ]
    df = pd.DataFrame(data)
    priorities = calculate_priorities(df)

    assert not priorities.empty
    explanation = priorities.iloc[0]["why_ranked"]
    assert isinstance(explanation, str)
    assert len(explanation) > 10
    assert "Filter Coffee" in explanation
