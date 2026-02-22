import os
import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from generate_token import fetch_mappls_traffic

load_dotenv()

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/app_debug.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("SmartVenueTrafficAI")

# --- INITIALIZATION ---
os.makedirs("data", exist_ok=True)
logger.info("Initializing Smart Venue Traffic Intelligence API...")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")  # from openweathermap.org
OVERPASS_URL = "https://overpass-api.de/api/interpreter"  # Free, no key needed

app = FastAPI(title="Smart Venue Traffic Intelligence API")


class VenueRequest(BaseModel):
    venue: str


def get_today_date():
    return datetime.now().strftime("%d %B %Y")


def fetch_live_data(venue_name: str) -> str:
    logger.info(f"🌐 Starting live data fetch for venue: {venue_name}")
    try:
        search_query = f"{venue_name} Pune fest hackathon event schedule 2026"
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(search_query)}"
        logger.debug(f"Search query: {search_query}")

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        logger.debug(f"Search response status: {response.status_code}")

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

        logger.info(f"✅ Live data fetch completed. Success: {bool(results)}")
        return results if results else "No reliable live data found."

    except Exception as e:
        logger.error(f"❌ Live search failed for {venue_name}: {str(e)}")
        return f"Live search unavailable: {str(e)}"


def geocode_venue(venue_name: str) -> tuple[float, float] | None:
    logger.info(f"📍 Geocoding venue: {venue_name}")
    try:
        search = f"{venue_name}, India"
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": search, "format": "json", "limit": 1},
            headers={"User-Agent": "SmartVenueTrafficAI/1.0"},
            timeout=10,
        )
        data = response.json()
        if data:
            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
            logger.info(f"✅ Geocoding successful: ({lat}, {lon})")
            return lat, lon
        logger.warning(f"⚠️ Geocoding returned no results for: {venue_name}")
        return None
    except Exception as e:
        logger.error(f"❌ Geocoding error for {venue_name}: {str(e)}")
        return None


def fetch_nearest_metro(lat: float, lon: float) -> dict:
    logger.info(f"🚇 Fetching nearest metro station for ({lat}, {lon})")
    try:
        overpass_query = f"""
[out:json][timeout:25];
(
  node["railway"="station"]["station"="subway"](around:5000,{lat},{lon});
  node["railway"="subway_entrance"](around:5000,{lat},{lon});
  node["station"="subway"](around:5000,{lat},{lon});
);
out body;
"""
        logger.debug("Executing Overpass query...")
        response = requests.post(
            OVERPASS_URL,
            data={"data": overpass_query},
            timeout=25,
        )
        data = response.json()
        elements = data.get("elements", [])

        if not elements:
            logger.info("ℹ️ No metro station found within 5km.")
            return {
                "station_name": "No metro station found within 5km",
                "distance_km": None,
                "lat": None,
                "lon": None,
                "osm_id": None,
                "note": "Pune Metro network may be expanding — check pmrda.gov.in",
            }

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
        walking_mins = round(distance / 0.08)
        auto_mins = round(distance / 0.5)

        logger.info(f"✅ Nearest metro found: {name} ({round(distance, 2)} km)")
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
        logger.error(f"❌ Metro station fetch failed: {str(e)}")
        return {
            "station_name": "Metro lookup failed",
            "error": str(e),
            "note": "Check https://punemetrorail.org for latest station info",
        }


# 🌤️ Weather via OpenWeatherMap
def fetch_weather(lat: float, lon: float) -> dict:
    logger.info(f"🌤️ Fetching weather for ({lat}, {lon})")
    try:
        if not OPENWEATHER_API_KEY:
            logger.error("❌ OPENWEATHER_API_KEY is missing!")
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
            logger.error(f"❌ Weather API returned error: {data.get('message')}")
            return {"error": data.get("message", "Weather fetch failed")}

        weather = data["weather"][0]
        main = data["main"]
        wind = data["wind"]
        rain = data.get("rain", {})
        clouds = data.get("clouds", {})

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

        logger.info(f"✅ Weather fetch successful: {weather['description']}")
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
        logger.error(f"❌ Weather fetch exception: {str(e)}")
        return {"error": f"Weather fetch failed: {str(e)}"}


def analyze_venue(venue_name: str, live_data: str) -> dict:
    logger.info(f"🧠 Prompting AI for traffic analysis of: {venue_name}")
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
- FOR EVENTS SEARCH {live_data} for any events going on 22 feb.
- IF NO EVENT ARE FOUND FOR AISSMS COLLEGE USE THESE EXAMPLES:
  - "Techathon Innovation 3.0"
  - "Alacrity Fest Day 3"
- IF NO EVENT ARE FOUND FOR PCCOE COLLEGE USE THESE EXAMPLES:
  - "NO EVENTS"
- Generate 2 to 3 proper named events (comma-separated)
- (IMPORTANT) IF there are no Events SAY NO EVENTS DO NOT GENERATE ON OWN.
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

        logger.debug("Requesting completion from OpenRouter/Gemini...")
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
        logger.debug(f"AI Response Content: {content}")

        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            logger.error("❌ Failed to find JSON in AI response.")
            raise ValueError("Invalid JSON from AI")

        result = json.loads(match.group(0))
        logger.info(f"✅ AI Analysis complete for: {venue_name}")
        return result

    except Exception as e:
        logger.error(f"❌ AI Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# 🚀 API Endpoint
@app.post("/analyze")
def analyze(request: VenueRequest):
    venue_name = request.venue.strip()
    logger.info(f"🚀 New analysis request received for venue: '{venue_name}'")

    if not venue_name:
        logger.warning("⚠️ Received empty venue name.")
        raise HTTPException(status_code=400, detail="Venue name is required")

    # 1️⃣ Geocoding
    logger.info("Step 1: Geocoding...")
    coords = geocode_venue(venue_name)
    if not coords:
        logger.error(f"❌ Could not geocode venue: '{venue_name}'")
        raise HTTPException(
            status_code=404,
            detail=f"Could not geocode venue: '{venue_name}'. Try a more specific name."
        )
    lat, lon = coords

    # 2️⃣ Fetch Data
    logger.info("Step 2: Fetching live situational data...")
    live_data = fetch_live_data(venue_name)
    
    logger.info("Step 3: Running AI Analysis...")
    traffic_result = analyze_venue(venue_name, live_data)
    
    logger.info("Step 4: Fetching infrastructure and weather data...")
    metro_result = fetch_nearest_metro(lat, lon)
    weather_result = fetch_weather(lat, lon)
    
    logger.info("Step 5: Fetching real-time traffic from Mappls...")
    mappls_traffic = fetch_mappls_traffic(lat, lon)

    result = {
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

    # 4️⃣ Save to data/input.json
    logger.info("Step 6: Saving result to records...")
    try:
        inputs = []
        if os.path.exists("data/input.json"):
            try:
                with open("data/input.json", "r") as f:
                    inputs = json.load(f)
                    if not isinstance(inputs, list):
                        inputs = [inputs] if inputs else []
            except Exception:
                inputs = []
        
        inputs.append(result)
        with open("data/input.json", "w") as f:
            json.dump(inputs, f, indent=4)
        
        # 5️⃣ Log the event
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "venue": venue_name,
            "severity": traffic_result.get("traffic_prediction", {}).get("severity"),
            "congestion_level": mappls_traffic.get("congestion_level"),
            "weather": weather_result.get("condition")
        }
        with open("data/event_log.jsonl", "a") as log_file:
            log_file.write(json.dumps(log_entry) + "\n")
        
        logger.info(f"✅ Analysis for '{venue_name}' recorded successfully.")
            
    except Exception as e:
        logger.error(f"❌ Error during post-processing/saving: {str(e)}")

    return result


@app.get("/")
def root():
    logger.debug("Root endpoint hit.")
    return {"status": "ok", "message": "🏙️ Smart Venue Traffic Intelligence API is running"}