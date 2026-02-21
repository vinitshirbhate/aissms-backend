import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# 🔑 OpenRouter Client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

app = FastAPI(title="Smart Venue Traffic Intelligence API")


# 📥 Request Schema
class VenueRequest(BaseModel):
    venue: str


# 📅 Dynamic Date
def get_today_date():
    return datetime.now().strftime("%d %B %Y")


# 🌐 Live Search (DuckDuckGo)
def fetch_live_data(venue_name: str) -> str:
    try:
        search_query = f"{venue_name} Pune fest hackathon event schedule 2026"
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(search_query)}"

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = ""

        items = soup.select(".result")
        for i, el in enumerate(items):
            if i >= 8:
                break

            title = el.select_one(".result__title")
            snippet = el.select_one(".result__snippet")

            title_text = title.get_text(strip=True) if title else ""
            snippet_text = snippet.get_text(strip=True) if snippet else ""

            if title_text or snippet_text:
                results += f"Title: {title_text}\nSnippet: {snippet_text}\n---\n"

        return results if results else "No reliable live data found."

    except Exception as e:
        return f"Live search unavailable: {str(e)}"


# 🤖 AI Analysis Function
def analyze_venue(venue_name: str, live_data: str) -> dict:
    try:
        system_prompt = f"""
You are a Government-grade Smart City Traffic Intelligence AI for Pune, India.

STRICT OUTPUT RULES:
- Return ONLY valid JSON
- No explanation
- No markdown
- No extra text outside JSON
- Follow schema EXACTLY

CRITICAL EVENT NAMING RULES:
- DO NOT use generic terms like:
  "Hackathon", "Workshop", "Regular Classes", "Event"
- Always generate REALISTIC NAMED EVENTS like:
  - "Techathon Innovation 3.0"
  - "Alacrity Fest Day 3"
  - "Innovation & AI Expo 2026"
  - "National Coding Challenge 2026"
- Generate 2 to 3 proper named events (comma-separated)

TODAY'S DATE: {get_today_date()}

Output JSON structure EXACTLY:
{{
  "venue": {{
    "name": "full venue name",
    "type": "stadium | college | concert_hall | festival_ground | transit_hub | hospital | mall | protest_site | other",
    "capacity": "estimated max capacity e.g. 45,000"
  }},
  "event_context": {{
    "likely_event_today": "2–3 proper named events (comma-separated)",
    "date": "DD Month YYYY",
    "estimated_attendance": "estimated crowd today"
  }},
  "traffic_prediction": {{
    "severity": "CLEAR | LOW | MODERATE | HIGH | CRITICAL",
    "congestion_index": 0,
    "confidence": 50,
    "peak_period": {{
      "start": "HH:MM",
      "end": "HH:MM",
      "label": "e.g. 6:30 PM – 9:00 PM",
      "description": "why this window is worst"
    }}
  }},
  "impact_zones": [
    {{ "radius": "0–500m", "level": 0, "roads_affected": "specific road names near venue" }},
    {{ "radius": "500m–2km", "level": 0, "roads_affected": "major connecting roads and junctions" }}
  ]
}}
"""

        user_prompt = f"""
VENUE NAME: {venue_name}

LIVE SEARCH DATA:
{live_data}

Return STRICT JSON only with proper event names (not generic).
"""

        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            temperature=0.25,
            max_tokens=650,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON safely
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ValueError("Invalid JSON from AI")

        return json.loads(match.group(0))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 🚀 API Endpoint (Uvicorn Ready)
@app.post("/analyze")
def analyze(request: VenueRequest):
    venue_name = request.venue.strip()

    if not venue_name:
        raise HTTPException(status_code=400, detail="Venue name is required")

    live_data = fetch_live_data(venue_name)
    result = analyze_venue(venue_name, live_data)

    return result