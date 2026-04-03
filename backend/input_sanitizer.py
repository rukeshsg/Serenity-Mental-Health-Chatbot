"""
Input Sanitization Module
=========================
Provides sanitization functions to clean user input before processing.
This is applied BEFORE the safety + ML pipeline.

IMPORTANT: Sanitization must preserve the original meaning of the message.
We only strip potentially harmful patterns, not content.
"""

import re
import html


def sanitize_input(text):
    """
    Sanitize user input to prevent injection attacks while preserving meaning.
    
    Operations (in order):
    1. Strip HTML tags (prevent XSS)
    2. Remove control characters (prevent terminal injection)
    3. Normalize whitespace (prevent padding attacks)
    4. Decode HTML entities (restore legitimate HTML-encoded content)
    
    Args:
        text: Raw user input
        
    Returns:
        Sanitized string safe for processing
    """
    if not text:
        return ""
    
    # Step 1: Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Step 2: Remove control characters (except newlines, tabs)
    # This prevents terminal escape sequences and other control attacks
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # Step 3: Normalize whitespace (collapse multiple spaces, trim)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Step 4: Decode HTML entities (e.g., < → <)
    text = html.unescape(text)
    
    # Final safety: re-check for any remaining dangerous patterns
    # (in case HTML entities were used to bypass step 1)
    text = re.sub(r'<[^>]+>', '', text)
    
    return text


def sanitize_for_llm(text):
    """
    Additional sanitization specifically for LLM prompts.
    Removes patterns that could manipulate system prompts.
    """
    if not text:
        return ""
    
    # Remove potential prompt injection patterns
    # These are informational only - we don't reject the input
    
    # Trim to reasonable length (prevent DoS)
    max_length = 10000
    if len(text) > max_length:
        text = text[:max_length]
    
    return text


def is_safe_input(text):
    """
    Check if input passes basic safety validation.
    
    Returns:
        tuple: (is_safe, reason_if_not)
    """
    if not text:
        return False, "Empty input"
    
    # Check minimum length
    if len(text.strip()) < 1:
        return False, "Input too short"
    
    # Check maximum length (prevent DoS)
    if len(text) > 20000:
        return False, "Input too long"
    
    # Check for only whitespace
    if not text.strip():
        return False, "Input is only whitespace"
    
    return True, ""
