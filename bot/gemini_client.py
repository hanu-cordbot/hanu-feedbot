import os
import time
import google.generativeai as genai
from typing import List, Dict

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = genai.GenerativeModel("gemini-2.5-flash")

def _parts(blocks: List[Dict]) -> List[Dict]:
    """Prepares the parts for the Gemini API call."""
    out: list[dict] = []
    for b in blocks:
        if b.get("type") == "text":
            out.append({"text": b["text"]})
    return out

def call_gemini(blocks: List[Dict], tries: int = 3) -> str:
    """Calls the Gemini API with a retry mechanism."""
    parts = _parts(blocks)
    for i in range(tries):
        try:
            rsp = MODEL.generate_content(parts)
            return rsp.text.strip()
        except Exception as exc:
            print(f"[Gemini error] {exc}  (attempt {i + 1}/{tries})")
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    return "" # Should not be reached, but added for safety
