"""
NLP Engine for Canteen Copilot.
"""

import re
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import NMF

SEVERITY_MAP = {
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

ASPECT_LEXICON: Dict[str, List[str]] = {
    "food_safety": [
        "hair", "insect", "cockroach", "fly", "flies", "worm", "caterpillar", "stone",
        "glass", "plastic", "staple", "bug", "foreign object", "dead", "contaminated",
        "baal", "keeda", "kida", "makkhi", "patthar"
    ],
    "hygiene": [
        "hygiene", "dirty", "unhygienic", "clean", "cleanliness", "grease", "greasy",
        "smell", "stinking", "dustbin", "unwashed", "bare hand", "sanitized", "washbasin",
        "drain", "dirty plate", "spoons dirty", "chhipkali", "ganda", "kachra", "badbu"
    ],
    "freshness": [
        "fresh", "freshness", "stale", "sour", "rubbery", "old batch", "spoiled",
        "rotten", "fermented", "curdled", "foul", "expired", "basi", "kharab", "sada"
    ],
    "taste": [
        "taste", "tasty", "salty", "salt", "namak", "spice", "spicy", "bland", "flavor",
        "flavour", "bitter", "sour", "sweet", "oily", "watery", "gravy", "overcooked",
        "undercooked", "burnt", "seasoning", "swad", "feeka", "mirchi", "kaccha", "jala"
    ],
    "temperature": [
        "temperature", "cold", "hot", "piping hot", "warm", "lukewarm", "steaming",
        "congealed", "freezing", "chilled", "thanda", "garam", "lukewarm"
    ],
    "wait_time": [
        "wait", "waiting", "queue", "line", "slow", "token", "delay", "time", "crowd",
        "turnaround", "hurry", "rush", "deri", "lamba line", "bheed", "intezar", "ghanto"
    ],
    "portion": [
        "portion", "quantity", "amount", "size", "little", "small serving", "tiny",
        "filling", "generous", "scanty", "less", "kam", "chhota", "pet nahi bhara"
    ],
    "staff_behavior": [
        "staff", "behavior", "behaviour", "rude", "polite", "cashier", "server", "shout",
        "attitude", "arrogant", "friendly", "uncle", "bhaiya", "gussa", "chilla"
    ],
    "price": [
        "price", "cost", "expensive", "cheap", "worth", "money", "overpriced", "rate",
        "rupees", "rs", "mehenga", "loot", "paisa vasool"
    ]
}

ASPECT_PATTERNS = {
    category: re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b", re.IGNORECASE)
    for category, keywords in ASPECT_LEXICON.items()
}

FALLBACK_LEXICON: Dict[str, float] = {
    "good": 0.5, "great": 0.8, "excellent": 0.9, "tasty": 0.7, "delicious": 0.85,
    "fresh": 0.6, "clean": 0.6, "fast": 0.5, "polite": 0.6, "filling": 0.5,
    "mast": 0.8, "badhiya": 0.8, "swad": 0.5, "hot": 0.3, "satisfied": 0.6,
    "bad": -0.6, "worst": -0.9, "awful": -0.85, "terrible": -0.9, "horrible": -0.9,
    "stale": -0.7, "salty": -0.6, "dirty": -0.8, "rude": -0.7, "slow": -0.5,
    "cold": -0.5, "thanda": -0.5, "basi": -0.7, "bakwas": -0.85, "ganda": -0.8,
    "hair": -0.95, "insect": -0.95, "cockroach": -0.99, "worm": -0.99, "vomit": -0.9,
    "watery": -0.5, "feeka": -0.5, "oily": -0.5, "burnt": -0.7, "poor": -0.6
}


def _get_vader_analyzer():
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except Exception:
        return None


_VADER_ANALYZER = None


def analyze_sentiment(
    text: str,
    use_huggingface: bool = False
) -> Tuple[float, str]:
    global _VADER_ANALYZER

    if not isinstance(text, str) or not text.strip():
        return 0.0, "neutral"

    if use_huggingface:
        try:
            from transformers import pipeline
            hf_pipe = pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-sentiment-latest", device=-1)
            res = hf_pipe(text[:200])[0]
            label_map = {"positive": "positive", "neutral": "neutral", "negative": "negative"}
            label = label_map.get(res["label"].lower(), "neutral")
            score = float(res["score"])
            if label == "negative":
                score = -score
            elif label == "neutral":
                score = 0.0
            return score, label
        except Exception:
            pass

    if _VADER_ANALYZER is None:
        _VADER_ANALYZER = _get_vader_analyzer()

    if _VADER_ANALYZER is not None:
        try:
            vs = _VADER_ANALYZER.polarity_scores(text)
            compound = vs["compound"]
            if compound >= 0.05:
                label = "positive"
            elif compound <= -0.05:
                label = "negative"
            else:
                label = "neutral"
            return round(compound, 3), label
        except Exception:
            pass

    words = re.findall(r"\w+", text.lower())
    scores = [FALLBACK_LEXICON[w] for w in words if w in FALLBACK_LEXICON]
    if scores:
        mean_score = sum(scores) / (len(scores) ** 0.5)
        compound = max(-1.0, min(1.0, mean_score))
    else:
        compound = 0.0

    if compound >= 0.1:
        label = "positive"
    elif compound <= -0.1:
        label = "negative"
    else:
        label = "neutral"

    return round(compound, 3), label


def extract_aspects(text: str) -> List[Dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        return []

    clauses = re.split(r"\b(but|however|although|and|aur|lekin|par|yet|while)\b|,|;", text, flags=re.IGNORECASE)
    clauses = [c.strip() for c in clauses if c and len(c.strip()) > 3]

    found_aspects: Dict[str, Dict[str, Any]] = {}

    for clause in clauses:
        clause_score, clause_label = analyze_sentiment(clause)
        for category, pattern in ASPECT_PATTERNS.items():
            match = pattern.search(clause)
            if match:
                keyword = match.group(0).lower()
                if category == "food_safety":
                    clause_score = min(clause_score, -0.7)
                    clause_label = "negative"

                if category not in found_aspects:
                    found_aspects[category] = {
                        "category": category,
                        "keyword": keyword,
                        "sentiment_score": clause_score,
                        "sentiment_label": clause_label,
                        "severity": SEVERITY_MAP.get(category, 1)
                    }
                else:
                    if clause_score < found_aspects[category]["sentiment_score"]:
                        found_aspects[category]["sentiment_score"] = clause_score
                        found_aspects[category]["sentiment_label"] = clause_label

    if not found_aspects:
        for category, pattern in ASPECT_PATTERNS.items():
            match = pattern.search(text)
            if match:
                overall_score, overall_label = analyze_sentiment(text)
                found_aspects[category] = {
                    "category": category,
                    "keyword": match.group(0).lower(),
                    "sentiment_score": overall_score,
                    "sentiment_label": overall_label,
                    "severity": SEVERITY_MAP.get(category, 1)
                }

    return list(found_aspects.values())


def detect_rating_mismatch(rating: int, sentiment_score: float) -> bool:
    if rating >= 4 and sentiment_score <= -0.25:
        return True
    if rating <= 2 and sentiment_score >= 0.35:
        return True
    return False


def enrich_feedback_dataframe(
    df: pd.DataFrame,
    use_huggingface: bool = False
) -> pd.DataFrame:
    enriched = df.copy()

    sentiments = []
    sentiment_labels = []
    aspect_lists = []
    primary_categories = []
    severities = []
    mismatch_flags = []

    for _, row in enriched.iterrows():
        comment = str(row.get("comment", ""))
        rating = int(row.get("rating", 3))
        existing_cat = str(row.get("issue_category", "none")).lower()

        score, label = analyze_sentiment(comment, use_huggingface=use_huggingface)
        sentiments.append(score)
        sentiment_labels.append(label)

        aspects = extract_aspects(comment)
        aspect_lists.append(aspects)

        if aspects:
            sorted_aspects = sorted(aspects, key=lambda a: (a["severity"], -a["sentiment_score"]), reverse=True)
            primary_cat = sorted_aspects[0]["category"]
            max_sev = sorted_aspects[0]["severity"]
        elif existing_cat != "none":
            primary_cat = existing_cat
            max_sev = SEVERITY_MAP.get(existing_cat, 1)
        else:
            primary_cat = "none"
            max_sev = 0

        primary_categories.append(primary_cat)
        severities.append(max_sev)

        is_mismatch = detect_rating_mismatch(rating, score)
        mismatch_flags.append(is_mismatch)

    enriched["sentiment_score"] = sentiments
    enriched["sentiment_label"] = sentiment_labels
    enriched["detected_aspects"] = aspect_lists
    enriched["predicted_category"] = primary_categories
    enriched["severity"] = severities
    enriched["is_mismatch"] = mismatch_flags

    if "issue_category" not in enriched.columns or enriched["issue_category"].str.lower().eq("none").mean() > 0.6:
        enriched["issue_category"] = enriched["predicted_category"]

    return enriched


def discover_topics(
    comments: List[str],
    n_topics: int = 5,
    top_words: int = 4
) -> List[Dict[str, Any]]:
    valid_comments = [c for c in comments if isinstance(c, str) and len(c.strip()) > 10]
    if len(valid_comments) < 20:
        return []

    stop_words = "english"
    custom_stops = {
        "food", "canteen", "today", "was", "the", "and", "good", "bad",
        "tha", "hai", "bahut", "yaar", "thi", "se", "me"
    }

    try:
        vectorizer = TfidfVectorizer(
            stop_words=stop_words,
            max_features=500,
            ngram_range=(1, 2),
            min_df=2
        )
        tfidf = vectorizer.fit_transform(valid_comments)
        nmf = NMF(n_components=n_topics, random_state=42, max_iter=200)
        nmf_features = nmf.fit_transform(tfidf)

        feature_names = vectorizer.get_feature_names_out()
        topics = []
        topic_doc_assignments = np.argmax(nmf_features, axis=1)

        for topic_idx, topic in enumerate(nmf.components_):
            top_indices = topic.argsort()[:-top_words - 1:-1]
            words = [feature_names[i] for i in top_indices if feature_names[i] not in custom_stops][:top_words]
            if not words:
                words = [feature_names[i] for i in top_indices[:top_words]]

            title = " & ".join(w.capitalize() for w in words[:2]) + " Concerns"
            count = int(np.sum(topic_doc_assignments == topic_idx))

            topics.append({
                "topic_id": topic_idx + 1,
                "title": title,
                "keywords": words,
                "count": count
            })

        return topics
    except Exception:
        return []
