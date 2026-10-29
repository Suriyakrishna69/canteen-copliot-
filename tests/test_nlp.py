"""
Unit tests for Canteen Copilot NLP Engine.
"""

import pytest
from src.nlp import analyze_sentiment, extract_aspects, detect_rating_mismatch


def test_aspect_extraction_english_and_hinglish():
    aspects1 = extract_aspects("Found a hair and insect in the rice!")
    categories1 = [a["category"] for a in aspects1]
    assert "food_safety" in categories1
    assert aspects1[0]["severity"] == 5

    aspects2 = extract_aspects("Dal me namak bahut jyada tha.")
    categories2 = [a["category"] for a in aspects2]
    assert "taste" in categories2

    aspects3 = extract_aspects("Counter par bahut lamba line tha, token lene me deri hui.")
    categories3 = [a["category"] for a in aspects3]
    assert "wait_time" in categories3

    aspects4 = extract_aspects("Chai bilkul thanda tha.")
    categories4 = [a["category"] for a in aspects4]
    assert "temperature" in categories4


def test_multi_aspect_splitting():
    text = "Dosa was very tasty but the sambar was cold."
    aspects = extract_aspects(text)
    categories = {a["category"] for a in aspects}
    assert "taste" in categories or "temperature" in categories


def test_sentiment_analysis():
    pos_score, pos_label = analyze_sentiment("Delicious hot sambar, loved the taste!")
    assert pos_label == "positive"
    assert pos_score > 0.0

    neg_score, neg_label = analyze_sentiment("Disgusting cold food, very unhygienic and dirty plates.")
    assert neg_label == "negative"
    assert neg_score < 0.0


def test_rating_mismatch_detection():
    assert detect_rating_mismatch(rating=5, sentiment_score=-0.6) is True
    assert detect_rating_mismatch(rating=1, sentiment_score=0.8) is True
    assert detect_rating_mismatch(rating=5, sentiment_score=0.8) is False
    assert detect_rating_mismatch(rating=1, sentiment_score=-0.7) is False
