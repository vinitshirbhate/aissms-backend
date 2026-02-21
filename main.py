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
from generate_token import fetch_mappls_traffic

load_dotenv()

# 🔑 OpenRouter Client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# 🔑 API Keys
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")  # from openweathermap.org
OVERPASS_URL = "https://overpass-api.de/api/interpreter"  # Free, no key needed

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

        for i, el in enumerate(soup.select(".result")):
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


# 📍 Geocode venue name → (lat, lon) using Nominatim (OpenStreetMap)
def geocode_venue(venue_name: str) -> tuple[float, float] | None:
    try:
        search = f"{venue_name}, Pune, India"
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": search, "format": "json", "limit": 1},
            headers={"User-Agent": "SmartVenueTrafficAI/1.0"},
            timeout=10,
        )
        data = response.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
        return None
    except Exception:
        return None


# 🚇 Nearest Metro Station via Overpass API (OpenStreetMap)
def fetch_nearest_metro(lat: float, lon: float) -> dict:
    try:
        # Overpass query: find nearest subway/metro station within 5km
        overpass_query = f"""
[out:json][timeout:25];
(
  node["railway"="station"]["station"="subway"](around:5000,{lat},{lon});
  node["railway"="subway_entrance"](around:5000,{lat},{lon});
  node["station"="subway"](around:5000,{lat},{lon});
);
out body;
"""
        response = requests.post(
            OVERPASS_URL,
            data={"data": overpass_query},
            timeout=25,
        )
        data = response.json()
        elements = data.get("elements", [])

        if not elements:
            return {
                "station_name": "No metro station found within 5km",
                "distance_km": None,
                "lat": None,
                "lon": None,
                "osm_id": None,
                "note": "Pune Metro network may be expanding — check pmrda.gov.in",
            }

        # Calculate distances and find closest
        def haversine(lat1, lon1, lat2, lon2):
            from math import radians, sin, cos, sqrt, atan2
            R = 6371
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
            return R * 2 * atan2(sqrt(a), sqrt(1 - a))

        nearest = min(
            elements,
            key=lambda e: haversine(lat, lon, e["lat"], e["lon"])
        )

        distance = haversine(lat, lon, nearest["lat"], nearest["lon"])
        name = nearest.get("tags", {}).get("name", "Unknown Station")
        walking_mins = round(distance / 0.08)   # avg 4.8 km/h walking
        auto_mins = round(distance / 0.5)        # avg 30 km/h auto

        return {
            "station_name": name,
            "distance_km": round(distance, 2),
            "walking_time_mins": walking_mins,
            "auto_time_mins": auto_mins,
            "lat": nearest["lat"],
            "lon": nearest["lon"],
            "osm_id": nearest.get("id"),
            "google_maps_link": f"https://www.google.com/maps/dir/?api=1&destination={nearest['lat']},{nearest['lon']}",
        }

    except Exception as e:
        return {
            "station_name": "Metro lookup failed",
            "error": str(e),
            "note": "Check https://punemetrorail.org for latest station info",
        }


# 🌤️ Weather via OpenWeatherMap
def fetch_weather(lat: float, lon: float) -> dict:
    try:
        if not OPENWEATHER_API_KEY:
            return {"error": "OPENWEATHER_API_KEY not set in .env"}

        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
            },
            timeout=10,
        )
        data = response.json()

        if data.get("cod") != 200:
            return {"error": data.get("message", "Weather fetch failed")}

        weather = data["weather"][0]
        main = data["main"]
        wind = data["wind"]
        rain = data.get("rain", {})
        clouds = data.get("clouds", {})

        # Traffic weather impact assessment
        condition = weather["main"].lower()
        if condition in ["thunderstorm", "tornado"]:
            traffic_impact = "SEVERE — Expect major delays and road closures"
        elif condition in ["rain", "drizzle", "snow"]:
            traffic_impact = "HIGH — Wet roads, reduced visibility, slower traffic"
        elif condition in ["mist", "fog", "haze", "smoke"]:
            traffic_impact = "MODERATE — Low visibility may slow down traffic"
        elif main["temp"] > 38:
            traffic_impact = "LOW-MODERATE — Extreme heat may affect peak hour traffic"
        else:
            traffic_impact = "LOW — Weather conditions are favorable for travel"

        return {
            "condition": weather["description"].title(),
            "temperature_c": main["temp"],
            "feels_like_c": main["feels_like"],
            "humidity_percent": main["humidity"],
            "wind_speed_kmh": round(wind["speed"] * 3.6, 1),
            "wind_direction_deg": wind.get("deg"),
            "visibility_km": round(data.get("visibility", 10000) / 1000, 1),
            "cloud_cover_percent": clouds.get("all"),
            "rain_last_1h_mm": rain.get("1h", 0),
            "traffic_weather_impact": traffic_impact,
        }

    except Exception as e:
        return {"error": f"Weather fetch failed: {str(e)}"}


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
- DO NOT use generic terms like "Hackathon", "Workshop", "Regular Classes", "Event"
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
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ValueError("Invalid JSON from AI")

        return json.loads(match.group(0))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 🚀 API Endpoint
@app.post("/analyze")
def analyze(request: VenueRequest):
    venue_name = request.venue.strip()

    if not venue_name:
        raise HTTPException(status_code=400, detail="Venue name is required")

    # 1️⃣ Geocode the venue
    coords = geocode_venue(venue_name)
    if not coords:
        raise HTTPException(
            status_code=404,
            detail=f"Could not geocode venue: '{venue_name}'. Try a more specific name."
        )
    lat, lon = coords

    # 2️⃣ Run all fetches
    live_data = fetch_live_data(venue_name)
    traffic_result = analyze_venue(venue_name, live_data)
    metro_result = fetch_nearest_metro(lat, lon)
    weather_result = fetch_weather(lat, lon)
    mappls_traffic = fetch_mappls_traffic(lat, lon)

    # 3️⃣ Merge and return
    return {
        **traffic_result,
        "location": {
            "latitude": lat,
            "longitude": lon,
            "google_maps_link": f"https://www.google.com/maps?q={lat},{lon}",
        },
        "nearest_metro_station": metro_result,
        "weather": weather_result,
        "mappls_live_traffic": {
            "Distance (km)": mappls_traffic.get("distance_km"),
            "Travel Time (min)": mappls_traffic.get("travel_time_min"),
            "Traffic Delay (min)": mappls_traffic.get("traffic_delay_min"),
            "Average Speed (km/h)": mappls_traffic.get("average_speed_kmh"),
            "Congestion Level": mappls_traffic.get("congestion_level")
        }
    }


@app.get("/")
def root():
    return {"status": "ok", "message": "🏙️ Smart Venue Traffic Intelligence API is running"}