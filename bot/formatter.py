import re
import os
import json
from typing import List, Dict

# *** FIX: Updated prompt to gracefully handle empty titles. ***
PROMPT_HEADER = """
You are a text formatter. Your task is to take a post's title and body, combine them, and apply Discord-flavored markdown. You will also provide a short summary.

**FORMATTING RULES:**
**For combining the Title and Body:** 
If the POST TITLE is not empty, start the output with the POST TITLE formatted as a main heading (`# **Title**`). 
Then, add the POST BODY. If the POST TITLE is empty, the output should consist ONLY of the POST BODY, with no heading.


**For text formatting:**
**Do NOT rewrite, remove, or change any of the original text.** Only add markdown.
Use `**bold**` for main headings or important phrases.
Use `*italics*` for emphasis.
Use `> ` for blockquotes if appropriate.
Remove hashtag walls but keep other links.
Preserve all original emojis.

**For paragraphing:**
**Each line in the raw input is a separate paragraph. Preserve these line breaks in the output by ensuring there is a blank line between each.**
Format lists using `- ` or `* `. 
If a newline from the post starts with an emoji, use that emoji instead.
If a newline from the post starts with a custom item (e.g. numbers), use that item instead.

**For URLs:**
**DO NOT convert URLs into markdown links like `[text](url)`. Leave all links as raw, plain text.**
**For links starting with "https://", add a <> wrapper around the link**

**For tl;dr:**
**The 'tl;dr' summary MUST be written in the same language as the original post.**

**OUTPUT TEMPLATE (USE EXACTLY):**
<MARKDOWN_FORMATTED_BODY>

-# tl;dr:
-# <summary sentence 1>
-# <summary sentence 2>
""".strip()


def build_prompt(entry: dict) -> List[Dict[str, str]]:
    """
    Creates the prompt structure that gemini_client.py expects.
    """
    # Load prompt sections from JSON
    prompt_file = os.path.join(os.getcwd(), 'system_prompt.json')
    prompt_parts = []
    if os.path.exists(prompt_file):
        try:
            sections = json.load(open(prompt_file, encoding='utf-8'))
            for sec in sections:
                prompt_parts.append({"type": "text", "text": sec.get('content', '')})
        except Exception:
            prompt_parts.append({"type": "text", "text": PROMPT_HEADER})
    else:
        prompt_parts.append({"type": "text", "text": PROMPT_HEADER})
    # Post title and body
    title = entry.get("title", "")
    body = entry.get('raw', '')
    prompt_parts.append({"type": "text", "text": f"POST TITLE: {title}"})
    prompt_parts.append({"type": "text", "text": f"POST BODY:\n{body}"})
    return prompt_parts

def split_reply(model_reply: str) -> tuple[str, str]:
    """Separates the model's response into (body, tldr) and cleans it up."""
    marker = "-# tl;dr:"
    parts = re.split(fr'\s*{re.escape(marker)}\s*', model_reply, maxsplit=1, flags=re.IGNORECASE)

    if len(parts) < 2:
        return (model_reply.strip(), "")

    body, tail = parts
    tldr = f"{marker}\n{tail.strip()}"
    return body.strip(), tldr

# Thread title generation prompt
THREAD_TITLE_PROMPT = """
You are a multilingual, culturally-aware AI assistant specializing in social media. Your primary function is to read a user's post from any language and distill its essence into a single, powerful title that perfectly reflects its vibe, voice, and—most importantly—its original language and dialect.
Your Guiding Principle: Mirror, Don't Translate. The title you generate must feel like it was written by the original poster, not by a machine translating concepts.
Your Process:
1. Identify the Language: Output MUST be in the same language as the post.
2. Analyze the Voice & Diction: Match slang, emotional tone, and formality.
3. Create a concise, catchy title channeling the post's energy.
4. Only focus on the subject. Exclude the author. For example, it should be 'ac cho e hỏi đầu năm có phải ktra sức khoẻ nữa ko ạ 😭', not 'Hanu Confessions: ac cho e hỏi đầu năm có phải ktra sức khoẻ nữa ko ạ 😭 '.
Return only the title as a single line.
"""

def build_thread_title_prompt(body: str) -> List[Dict[str, str]]:
    """
    Build prompt for AI to generate thread title from post body.
    """
    return [
        {"type": "text", "text": THREAD_TITLE_PROMPT},
        {"type": "text", "text": f"POST BODY:\n{body}"}
    ]

def format_vietnamese_date(dt):
    """Formats a pendulum datetime into a Vietnamese string."""
    days = {
        "Monday": "sao đã thứ hai r...", "Tuesday": "thứ ba", "Wednesday": "thứ tư, ơ vl đã được nửa tuần r này",
        "Thursday": "thứ năm", "Friday": "thứ sáu", "Saturday": "thứ bảy r ae !!!!!", "Sunday": "chủ nhật"
    }
    day_of_week = days[dt.format('dddd')]
    return f"# {day_of_week.capitalize()}, ngày {dt.day} tháng {dt.month} năm {dt.year}"
