"""
Fallback Intent Engine (Keyword-based)
====================================
Used when the BiLSTM model is unavailable.
Provides basic keyword-based intent detection as a fallback.
"""

def predict_intent(text):
    """
    Predict intent using keyword matching.
    This is a simple fallback - not as accurate as BiLSTM.
    
    Returns:
        tuple: (intent, confidence)
    """
    text = text.lower()
    
    # Define keyword patterns for each intent
    intent_keywords = {
        "greeting": ["hello", "hi", "hey", "hii", "yo", "hi there", "hello there", "good morning", "good evening", "good night"],
        "depression": ["sad", "depressed", "empty", "hopeless", "worthless", "tired of trying", "can't go on", "better off dead", "no reason to live"],
        "anxiety": ["anxious", "worried", "scared", "panic", "nervous", "overwhelmed", "stress", "stressed", "can't breathe", "racing thoughts"],
        "anger": ["angry", "mad", "furious", "hate", "irritated", "annoyed", "frustrated", "rage"],
        "sadness": ["sad", "crying", "tears", "lonely", "alone", "miss", "hurt", "pain"],
        "stress": ["stressed", "overwhelmed", "too much", "can't handle", "pressure", "deadline"],
        "fear": ["scared", "afraid", "fear", "terrified", "horrified", "panic"],
        "distress": ["not okay", "not fine", "breaking down", "falling apart", "can't cope"],
    }
    
    best_intent = "normal"
    best_confidence = 0.5
    
    # Check each intent's keywords
    for intent, keywords in intent_keywords.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            confidence = min(0.5 + (matches * 0.1), 0.9)  # Simple confidence calculation
            if confidence > best_confidence:
                best_intent = intent
                best_confidence = confidence
    
    return best_intent, best_confidence
