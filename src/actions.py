"""
Action Recommendations & Review Reply Generator for Canteen Copilot.
"""

import os
from typing import Dict, Any, List, Optional
import pandas as pd

TEMPLATE_ACTIONS: Dict[str, Dict[str, str]] = {
    ("taste", "Dal Tadka"): {
        "title": "Recalibrate Salt & Spice Ratios",
        "action": "Reduce salt in Dal Tadka recipe by ~15-20%. Implement a mandatory head-cook taste test batch check at 11:30 AM before lunch rush.",
        "preventive": "Use pre-measured salt dispensers rather than manual hand-tossing.",
        "timeframe": "Immediate (Next Service)"
    },
    ("freshness", "Paneer Butter Masala"): {
        "title": "Restructure Friday Dairy Supply Chain",
        "action": "Switch dairy vendor delivery for paneer from Wednesday to Thursday afternoon. Inspect refrigerator holding temperature (keep strictly below 4°C).",
        "preventive": "Mark batch receipt dates with color-coded stickers. Discard unsold dairy batches after 48 hours.",
        "timeframe": "24-48 Hours"
    },
    ("wait_time", "Idli Sambar"): {
        "title": "Split Morning Token & Pickup Counters",
        "action": "Designate a dedicated express token line for pre-set breakfast combos (Idli/Vada) between 8:00 AM - 9:30 AM on Mondays.",
        "preventive": "Pre-pack standard sambar and chutney bowls 15 minutes prior to peak 8:30 AM rush.",
        "timeframe": "By Next Monday"
    },
    ("taste", "Chicken Curry"): {
        "title": "Recipe Standard Audit & Meat Sourcing Check",
        "action": "Audit current oil and spice paste formulation. Check meat batch freshness with poultry supplier and restore original week 1-5 simmer recipe.",
        "preventive": "Supervise gravy emulsification and sample seasoning daily at 12:00 PM.",
        "timeframe": "Within 2 Days"
    },
    ("food_safety", "ANY"): {
        "title": "Immediate Kitchen Sanitation & Pest Audit",
        "action": "Halt affected prep line immediately. Conduct emergency deep inspection of dry storage bins, grain sacks, and cook line. Mandate hairnets and beard guards.",
        "preventive": "Schedule bi-weekly pest control treatment and introduce digital food safety inspection checklist.",
        "timeframe": "IMMEDIATE (Within 2 Hours)"
    }
}

GENERIC_CATEGORY_ACTIONS: Dict[str, Dict[str, str]] = {
    "food_safety": {
        "title": "Emergency Contamination Protocol",
        "action": "Quarantine food batch, inspect raw ingredient storage, and conduct immediate hygiene briefing with kitchen staff.",
        "preventive": "Enforce strict kitchen attire (hairnets, aprons, gloves) and seal open ingredient bins.",
        "timeframe": "Immediate"
    },
    "hygiene": {
        "title": "Deep Kitchen & Utensil Sanitation Protocol",
        "action": "Increase dishwashing rinse temperature to >75°C. Re-sanitize stainless steel trays and table cleaning cloths with disinfectant.",
        "preventive": "Institute hourly dining hall wipe-down checks signed by floor supervisor.",
        "timeframe": "24 Hours"
    },
    "freshness": {
        "title": "Ingredient Shelf-Life & Storage Audit",
        "action": "Audit refrigeration temperatures and implement FIFO (First-In-First-Out) labeling on all raw perishables.",
        "preventive": "Reduce batch prep sizes by 25% and order daily perishable deliveries.",
        "timeframe": "1-2 Days"
    },
    "taste": {
        "title": "Recipe Calibration & Supervisor Taste Test",
        "action": "Standardize spice and salt measurements using calibrated scoops rather than eyeballing. Require sous-chef taste sign-off.",
        "preventive": "Document standardized recipe cards at every cooking station.",
        "timeframe": "Next Service"
    },
    "temperature": {
        "title": "Hot-Holding Equipment Maintenance",
        "action": "Inspect bain-marie water levels and heating coils. Ensure food stays above 63°C during service.",
        "preventive": "Use digital probe thermometers at 30-minute intervals during lunch and dinner.",
        "timeframe": "Same Day"
    },
    "wait_time": {
        "title": "Counter Flow Optimization & Peak Staffing",
        "action": "Add an extra cashier or digital QR ordering counter during peak 8:30-9:30 AM and 1:00-2:00 PM rushes.",
        "preventive": "Pre-portion high-demand sides (chutney, sambar, raita) before counter opens.",
        "timeframe": "Within 3 Days"
    },
    "portion": {
        "title": "Standard Portion Ladle Implementation",
        "action": "Equip serving staff with volume-calibrated portion ladles (e.g. 150ml for curries, 200g for rice).",
        "preventive": "Place visual serving guide charts behind counters for staff guidance.",
        "timeframe": "Immediate"
    },
    "staff_behavior": {
        "title": "Customer Service & Conflict Resolution Workshop",
        "action": "Hold a 30-minute morning briefing emphasizing polite communication and de-escalation with students.",
        "preventive": "Reward top-rated counter personnel monthly with recognition incentives.",
        "timeframe": "This Week"
    },
    "price": {
        "title": "Value & Combo Meal Review",
        "action": "Introduce student combo platters to balance perceived meal value.",
        "preventive": "Publish clear price breakdowns displaying ingredient quality standards.",
        "timeframe": "Committee Review"
    }
}


def get_action_recommendation(
    item: str,
    issue_category: str,
    sample_comments: Optional[List[str]] = None,
    stats: Optional[Dict[str, Any]] = None,
    use_llm: bool = True
) -> Dict[str, str]:
    lookup_key = (issue_category.lower(), item)
    if lookup_key in TEMPLATE_ACTIONS:
        rec = TEMPLATE_ACTIONS[lookup_key].copy()
    elif (issue_category.lower(), "ANY") in TEMPLATE_ACTIONS:
        rec = TEMPLATE_ACTIONS[(issue_category.lower(), "ANY")].copy()
    else:
        rec = GENERIC_CATEGORY_ACTIONS.get(
            issue_category.lower(),
            {
                "title": f"Review {issue_category.capitalize()} Standards for {item}",
                "action": f"Conduct focused review of preparation and service process for {item}.",
                "preventive": "Establish weekly inspection check.",
                "timeframe": "Within 48 Hours"
            }
        ).copy()

    gemini_key = os.getenv("GEMINI_API_KEY")
    if use_llm and gemini_key and gemini_key != "MY_GEMINI_API_KEY":
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            prompt = (
                f"You are the executive canteen quality supervisor. Recommend a specific, highly practical 2-sentence action for the kitchen staff.\n"
                f"Item: {item}\n"
                f"Issue Category: {issue_category}\n"
                f"Sample student comments: {sample_comments or []}\n"
                f"Keep it realistic for a college canteen with actionable kitchen steps."
            )
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if resp.text:
                rec["action"] = resp.text.strip()
        except Exception:
            pass

    return rec


def generate_draft_reply(
    student_comment: str,
    item: str,
    issue_category: str,
    rating: int = 1,
    use_llm: bool = True
) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if use_llm and gemini_key and gemini_key != "MY_GEMINI_API_KEY":
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            prompt = (
                f"Write a polite, warm, and professional 3-sentence response from the Canteen Management Committee to a student review.\n"
                f"Item: {item}\n"
                f"Rating: {rating}/5\n"
                f"Student Feedback: \"{student_comment}\"\n"
                f"Acknowledge the issue, explain the corrective step being taken, and invite them back."
            )
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            if resp.text:
                return resp.text.strip()
        except Exception:
            pass

    templates = {
        "food_safety": (
            f"Dear student, thank you for alerting us immediately. We take food safety matters with absolute gravity. "
            f"The kitchen supervisor has halted the {item} batch and initiated an emergency inspection. "
            f"Please stop by the canteen manager's office so we can issue a full refund and personally share our resolution."
        ),
        "hygiene": (
            f"Dear student, we apologize sincerely for the hygiene standards you experienced with {item}. "
            f"We have reiterated strict sanitation protocols with our dishwashing and counter team today. "
            f"Your feedback helps us maintain high campus dining standards."
        ),
        "taste": (
            f"Dear student, thank you for your candid feedback regarding {item}. "
            f"Our culinary team has reviewed the seasoning and cooking parameters today to ensure consistent taste. "
            f"We hope to serve you a much better meal on your next visit!"
        ),
        "wait_time": (
            f"Dear student, we appreciate your patience and apologize for the morning rush delays. "
            f"We are streamlining our token counters to expedite serving times during peak hours. "
            f"Thank you for helping us improve daily flow."
        )
    }
    return templates.get(
        issue_category.lower(),
        f"Dear student, thank you for your feedback regarding {item}. We have shared your comments with our kitchen supervisors to make immediate adjustments. We hope to serve you better next time!"
    )
