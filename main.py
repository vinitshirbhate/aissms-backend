import os
import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
from generate_token import fetch_mappls_traffic
from fastapi.middleware.cors import CORSMiddleware

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

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") 
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

app = FastAPI(title="Smart Venue Traffic Intelligence API")

# --- CORS CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DECISION SYSTEM CONSTANTS ---
SYSTEM_PROMPT_DECISION = """
You are a Government-grade AI Traffic Control System for Pune, India.
Your task is to analyze structured traffic state data and produce actionable traffic management decisions.
STRICT RULES:
- Output ONLY valid JSON
- No explanation
- No markdown
- No extra text
- Prioritize safety and congestion reduction
- Use realistic traffic engineering actions
"""

OUTPUT_SCHEMA_DECISION = """
Return JSON in EXACT format:
{
  "decision_summary": "short explanation",
  "priority_level": "low | medium | high | critical",
  "signal_actions": [
    {
      "junction_area": "name",
      "east_west_green_time_sec": number,
      "north_south_green_time_sec": number,
      "reason": "why"
    }
  ],
  "traffic_management_actions": ["action1", "action2"],
  "public_advisories": ["message1", "message2"],
  "suggested_reroute_waypoints": [
    {"name": "Location Name", "lat": 18.524, "lon": 73.847}
  ],
  "risk_assessment": {
    "choke_probability": 0.0,
    "crash_risk": 0.0,
    "pedestrian_density": "low | moderate | high"
  },
  "map_visualization_flags": {
    "highlight_event_zone": true,
    "highlight_congestion": true,
    "show_metro_option": true,
    "alert_level": "green | orange | red"
  },
  "next_review_in_minutes": number,
  "confidence": 0.0
}
"""

class VenueRequest(BaseModel):
    venue: str

def get_today_date():
    return datetime.now().strftime("%d %B %Y")

def fetch_live_data(venue_name: str) -> str:
    try:
        search_query = f"{venue_name} Pune fest hackathon event schedule 2026"
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(search_query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        results = ""
        for i, el in enumerate(soup.select(".result")):
            if i >= 8: break
            title = el.select_one(".result__title")
            snippet = el.select_one(".result__snippet")
            title_text = title.get_text(strip=True) if title else ""
            snippet_text = snippet.get_text(strip=True) if snippet else ""
            if title_text or snippet_text:
                results += f"Title: {title_text}\nSnippet: {snippet_text}\n---\n"
        return results if results else "No reliable live data found."
    except Exception as e:
        return f"Live search unavailable: {str(e)}"

def geocode_venue(venue_name: str) -> tuple[float, float] | None:
    try:
        search = f"{venue_name}, India"
        response = requests.get("https://nominatim.openstreetmap.org/search",
            params={"q": search, "format": "json", "limit": 1},
            headers={"User-Agent": "SmartVenueTrafficAI/1.0"}, timeout=10)
        data = response.json()
        if data: return float(data[0]["lat"]), float(data[0]["lon"])
        return None
    except Exception: return None

def fetch_nearest_metro(lat: float, lon: float) -> dict:
    try:
        overpass_query = f'[out:json][timeout:25];(node["railway"="station"]["station"="subway"](around:5000,{lat},{lon});node["railway"="subway_entrance"](around:5000,{lat},{lon});node["station"="subway"](around:5000,{lat},{lon}););out body;'
        response = requests.post(OVERPASS_URL, data={"data": overpass_query}, timeout=25)
        data = response.json()
        elements = data.get("elements", [])
        if not elements: return {"station_name": "None", "distance_km": None}
        def haversine(lat1, lon1, lat2, lon2):
            from math import radians, sin, cos, sqrt, atan2
            R = 6371
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
            return R * 2 * atan2(sqrt(a), sqrt(1 - a))
        nearest = min(elements, key=lambda e: haversine(lat, lon, e["lat"], e["lon"]))
        distance = haversine(lat, lon, nearest["lat"], nearest["lon"])
        return {"station_name": nearest.get("tags", {}).get("name", "Unknown"), "distance_km": round(distance, 2)}
    except Exception: return {"station_name": "Error", "distance_km": None}

def fetch_weather(lat: float, lon: float) -> dict:
    try:
        if not OPENWEATHER_API_KEY: return {"error": "No key"}
        
        response = requests.get("https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}, timeout=10)
        data = response.json()
        if data.get("cod") != 200: return {"error": "API error"}
        weather = data["weather"][0]
        return {"condition": weather["description"].title(), "temperature_c": data["main"]["temp"]}
    except Exception as e: return {"error": str(e)}

def analyze_venue(venue_name: str, live_data: str) -> dict:
    try:
        system_prompt = f"You are a Pune Smart City Traffic AI. Return ONLY JSON. Search {live_data}. Output keys: venue(name, type, capacity), event_context(likely_event_today, date, estimated_attendance), traffic_prediction(severity, congestion_index, confidence, peak_period(start, end, label, description)), impact_zones(radius, level, roads_affected)."
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            temperature=0.25,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"VENUE: {venue_name}\nLIVE DATA: {live_data}"}]
        )
        content = response.choices[0].message.content.strip()
        match = re.search(r"\{[\s\S]*\}", content)
        return json.loads(match.group(0))
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
def analyze(request: VenueRequest):
    venue_name = request.venue.strip()
    coords = geocode_venue(venue_name)
    if not coords: raise HTTPException(status_code=404, detail="Geocoding failed")
    lat, lon = coords
    live_data = fetch_live_data(venue_name)
    traffic_result = analyze_venue(venue_name, live_data)
    metro_result = fetch_nearest_metro(lat, lon)
    weather_result = fetch_weather(lat, lon)
    mappls_traffic = fetch_mappls_traffic(lat, lon)
    result = {**traffic_result, "location": {"latitude": lat, "longitude": lon}, "nearest_metro_station": metro_result, "weather": weather_result, "mappls_live_traffic": mappls_traffic}
    try:
        if os.path.exists("data/input.json"):
            with open("data/input.json", "r") as f: inputs = json.load(f)
        else: inputs = []
        inputs.append(result)
        with open("data/input.json", "w") as f: json.dump(inputs, f, indent=4)
    except Exception: pass
    return result

@app.post("/output")
def generate_output_decision():
    input_path = "data/input.json"
    output_path = "data/output.json"
    if not os.path.exists(input_path): raise HTTPException(status_code=404, detail="No input")
    with open(input_path, "r") as f: input_data = json.load(f)[-1]
    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        temperature=0.2,
        messages=[{"role": "system", "content": SYSTEM_PROMPT_DECISION}, {"role": "user", "content": f"INPUT:\n{json.dumps(input_data)}\n\nSCHEMA:\n{OUTPUT_SCHEMA_DECISION}"}]
    )
    decision = json.loads(re.search(r"\{[\s\S]*\}", response.choices[0].message.content).group(0))
    if os.path.exists(output_path):
        with open(output_path, "r") as f: outputs = json.load(f)
    else: outputs = []
    outputs.append(decision)
    with open(output_path, "w") as f: json.dump(outputs, f, indent=4)
    return decision

@app.get("/inputs")
def get_inputs():
    if os.path.exists("data/input.json"):
        with open("data/input.json", "r") as f: return json.load(f)
    return []

@app.get("/outputs")
def get_outputs():
    if os.path.exists("data/output.json"):
        with open("data/output.json", "r") as f: return json.load(f)
    return []

@app.get("/data")
def get_all_data():
    inputs = []
    outputs = []
    if os.path.exists("data/input.json"):
        with open("data/input.json", "r") as f:
            inputs = json.load(f)
    if os.path.exists("data/output.json"):
        with open("data/output.json", "r") as f:
            outputs = json.load(f)
    return {"inputs": inputs, "outputs": outputs}

@app.get("/map")
def get_map():
    return FileResponse("index.html")

@app.get("/output.json")
def get_output_json():
    if os.path.exists("data/output.json"):
        return FileResponse("data/output.json")
    return {"error": "not found"}

@app.get("/")
def root():
    return {"status": "ok", "map_dashboard": "/map"}
