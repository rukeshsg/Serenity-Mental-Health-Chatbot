import os
import re

import requests

# Load API key from environment - fallback to None if not set
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY_ANALYZER")
if not OPENROUTER_API_KEY:
    # Try to get from .env file
    try:
        from dotenv import load_dotenv

        load_dotenv()
        OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY_ANALYZER")
    except ImportError:
        pass

# If still not set, use a placeholder for testing
if not OPENROUTER_API_KEY:
    print("??  WARNING: OPENROUTER_API_KEY_ANALYZER not set. Using keyword-based fallback.")
    OPENROUTER_API_KEY = None


def _keyword_situation_hint(text_lower: str) -> str:
    """Deterministic fallback to prevent third-person false positives."""
    if not text_lower:
        return "normal"

    has_first_person = bool(re.search(r"\b(i|i'm|im|i've|ive|me|myself)\b", text_lower))
    has_third_person_context = bool(
        re.search(
            r"\b(my friend|my friends|my sister|my brother|my mother|my father|my mom|my dad|my family|he|she|they|someone)\b",
            text_lower,
        )
    )

    self_harm_keywords = [
        "kill myself", "want to die", "end my life", "hurt myself", "harm myself",
        "self harm", "suicide", "can't live anymore", "cannot live anymore",
        "don't want to live", "dont want to live", "ending everything",
        "end everything", "feel like ending everything", "end it all"
    ]
    for kw in self_harm_keywords:
        if kw in text_lower and (has_first_person or not has_third_person_context):
            return "self_harm"

    direct_user_abuse_keywords = [
        "i am being abused", "im being abused", "i'm being abused",
        "someone is abusing me", "someone abused me", "someone is hurting me",
        "someone hurt me", "he is abusing me", "she is abusing me", "they are abusing me",
        "i am being harassed", "i'm being harassed", "im being harassed",
        "someone is harassing me", "someone harassed me",
        "i am unsafe", "i'm unsafe", "i feel unsafe", "i am not safe", "i'm not safe",
    ]
    for kw in direct_user_abuse_keywords:
        if kw in text_lower:
            return "abuse"

    abuse_keywords = [
        "abuse", "abused", "harassment", "harassed", "assault", "unsafe",
        "hit me", "beating me", "beat me", "beaten", "beated", "bullied", "hurt me"
    ]
    for kw in (
        "hit me", "beating me", "beat me", "beaten", "beated", "hurt me",
        "abuse me", "abused me", "harass me", "harassed me", "assaulted me",
        "i am abused", "i was abused", "i am unsafe", "i feel unsafe"
    ):
        if kw in text_lower:
            return "abuse"

    third_person_keywords = [
        "my friend wants to die", "my sister wants to die", "my brother wants to die",
        "my mother wants to die", "my father wants to die", "my mom wants to die",
        "my dad wants to die", "he wants to die", "she wants to die", "they want to die",
        "someone wants to die", "my friend wants to harm themselves", "my friend is suicidal",
        "my friend can't live anymore", "my friend cannot live anymore",
        "my sister can't live anymore", "my brother can't live anymore",
        "he can't live anymore", "she can't live anymore", "they can't live anymore",
        "he wants to harm himself", "she wants to harm herself", "they want to harm themselves",
        "my friend is being abused", "my friend is abused", "he is being abused",
        "she is being abused", "they are being abused", "someone is being abused", "someone is abused"
    ]
    for kw in third_person_keywords:
        if kw in text_lower:
            return "third_person"

    # Generic abuse fallback only when the text does not look third-person focused
    if has_first_person and not has_third_person_context:
        for kw in abuse_keywords:
            if kw in text_lower:
                return "abuse"

    return "normal"


def analyze_situation(user_text):
    """
    Analyze the situation to determine perspective (self_harm, third_person, abuse, normal).
    """
    text_lower = (user_text or "").lower().strip()

    # Deterministic safety-first routing to avoid misclassification in mixed phrases
    local_hint = _keyword_situation_hint(text_lower)
    if local_hint in ("self_harm", "abuse"):
        return local_hint

    # Return deterministic result if API key is not available
    if not OPENROUTER_API_KEY:
        return local_hint

    system_prompt = """
You are a strict classifier.

Your job is to understand WHO the danger is about, not just the words.

Classify the message into ONLY ONE of these labels:

self_harm -> The user is talking about harming themselves (I, me, myself).
third_person -> The user is talking about someone else harming themselves (he, she, friend, family, someone).
abuse -> The user talks about abuse, harassment, violence.
normal -> None of the above.

CRITICAL RULES:
- Focus on WHO is being harmed.
- If the user says they are harmed or unsafe (I/me/myself), it is NOT third_person, even if friend/friends/family are mentioned.
- Use third_person only when the risk is about someone else.
- Only choose self_harm if the user clearly refers to themselves.
- Ignore movie/news examples.
- Output ONLY the label.
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "meta-llama/llama-3-8b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                "temperature": 0,
            },
            timeout=15,
        )

        result = response.json()
        label = result["choices"][0]["message"]["content"].strip().lower()

        # Safety fallback in case model answers strangely
        if label not in ["self_harm", "third_person", "abuse", "normal"]:
            return local_hint

        # Guardrail: do not allow third_person when deterministic rule says self-harm/abuse
        if label == "third_person" and local_hint in ("self_harm", "abuse"):
            return local_hint

        return label

    except Exception:
        return local_hint
