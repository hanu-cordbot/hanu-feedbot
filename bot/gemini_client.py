import os
import time
import google.generativeai as genai
from typing import List, Dict, Optional

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Primary and fallback models
PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"

# Initialize both models
PRIMARY = genai.GenerativeModel(PRIMARY_MODEL)
FALLBACK = genai.GenerativeModel(FALLBACK_MODEL)

def _parts(blocks: List[Dict]) -> List[Dict]:
    """Prepares the parts for the Gemini API call."""
    out: list[dict] = []
    for b in blocks:
        if b.get("type") == "text":
            out.append({"text": b["text"]})
    return out

def call_gemini(blocks: List[Dict], tries: int = 3) -> str:
    """
    Calls the Gemini API with fallback to flash-lite on rate limits.
    
    Args:
        blocks: List of content blocks to send to Gemini
        tries: Number of retry attempts
        
    Returns:
        Generated text response
    """
    parts = _parts(blocks)
    
    # First try with primary model
    for i in range(tries):
        try:
            rsp = PRIMARY.generate_content(parts)
            return rsp.text.strip()
        except Exception as exc:
            error_str = str(exc).lower()
            
            # Check if it's a rate limit error
            if "rate limit" in error_str or "quota" in error_str or "429" in error_str:
                print(f"[WARNING] Rate limit hit on {PRIMARY_MODEL}, falling back to {FALLBACK_MODEL}")
                
                # Try with fallback model
                try:
                    fallback_rsp = FALLBACK.generate_content(parts)
                    return fallback_rsp.text.strip()
                except Exception as fallback_exc:
                    print(f"[ERROR] Fallback model also failed: {fallback_exc}")
            
            print(f"[Gemini error] {exc} (attempt {i + 1}/{tries})")
            
            # Last attempt failed
            if i == tries - 1:
                return "Sorry, I couldn't generate a summary at this time."
                
            # Exponential backoff
            time.sleep(2 ** i)
    
    return ""  # Should not be reached, but added for safety