"""
Garcia Folklorico Studio -- GBP Post Generator
Uses Claude API to draft bilingual Google Business Profile "What's New" posts.
Max 1500 characters. Plain text only. Ends with a call to action.
"""

import json
import os
from pathlib import Path

import anthropic

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "gbp_config.json"

# Garcia-specific context for Claude
STUDIO_CONTEXT = """Garcia Folklorico Studio is a folklorico dance school in Oxnard, California,
located at 2012 Saviers Rd. Known as "La Casa del Folklor", the studio teaches traditional
Mexican folklorico dance to children and teens. Classes include Mommy & Me (ages 1.5-3),
Semillas (ages 3-5), Botones de Flor (ages 6-8), Elementary (ages 9-11), and Raices
(high school). The studio also offers affordable rental space for dance rehearsals,
events, and performances. Classes run in seasonal blocks (2-3 months each).
The studio serves families in Oxnard, Ventura County, and surrounding communities."""

TYPE_GUIDANCE = {
    "registration": (
        "Write an inviting post about class registration being open. "
        "Mention age groups available and encourage parents to sign up their children."
    ),
    "class_spotlight": (
        "Spotlight a specific class, describing what students learn, "
        "the age group, and why it's a great fit for kids."
    ),
    "cultural": (
        "Share something about folklorico dance culture, history, or traditions. "
        "Connect it to what students experience at the studio."
    ),
    "studio_rental": (
        "Highlight the studio rental option for dance groups, events, "
        "and rehearsals. Mention competitive pricing and the location."
    ),
    "event": (
        "Promote an upcoming performance, recital, or community event "
        "involving Garcia Folklorico Studio students."
    ),
    "seasonal": (
        "Write a culturally relevant seasonal post connecting folklorico "
        "dance to a holiday, celebration, or time of year."
    ),
}


def _get_anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")
    return key


def _build_tool():
    return {
        "name": "submit_gbp_post",
        "description": "Submit a completed Google Business Profile What's New post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "Post body text. Plain text only -- no HTML, no markdown, no hashtags, "
                        "no bullet points, no asterisks. Must be under 1500 characters total. "
                        "Must mention 'Garcia Folklorico Studio' by name at least once. "
                        "Must reference Oxnard or Ventura County. "
                        "Must end with a clear call to action."
                    ),
                }
            },
            "required": ["summary"],
        },
    }


def _build_prompt(topic: dict) -> str:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    topic_type = topic.get("type", "registration")
    subject = topic.get("subject", "folklorico dance classes Oxnard CA")
    cta_url = config.get("post_cta_url", "https://garciafolklorico.com")
    guidance = TYPE_GUIDANCE.get(topic_type, TYPE_GUIDANCE["registration"])

    return f"""You are writing a Google Business Profile "What's New" post for Garcia Folklorico Studio.

{STUDIO_CONTEXT}

POST TOPIC: {subject}
POST TYPE: {guidance}

STRICT REQUIREMENTS:
1. Plain text only -- no HTML, no markdown, no hashtags, no bullet points, no asterisks
2. Maximum 1,500 characters total (count carefully -- Google enforces this hard limit)
3. Mention "Garcia Folklorico Studio" by name at least once
4. Reference Oxnard or Ventura County naturally
5. The post should feel warm, welcoming, and community-oriented -- not salesy
6. End with a clear call to action pointing readers to: {cta_url}
7. Include a brief Spanish closing line (1-2 sentences) to connect with bilingual families
8. No competitor names, no hashtags (they are not clickable on GBP)

Write the post now."""


def generate_post(topic: dict) -> dict:
    """
    Generate a GBP post for the given topic.
    Returns: {{'summary': str}}
    """
    prompt = _build_prompt(topic)
    client = anthropic.Anthropic(api_key=_get_anthropic_api_key())
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        tools=[_build_tool()],
        tool_choice={"type": "tool", "name": "submit_gbp_post"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_gbp_post":
            return block.input

    raise ValueError("Claude did not return a tool use response.")
