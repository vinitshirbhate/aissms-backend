# FLUX — Traffic Intelligence API

AI-powered traffic surge prediction for any Indian venue.  
**One input → full prediction.** Powered by Gemini 1.5 Flash + FastAPI.

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your Gemini API key (free at https://aistudio.google.com/app/apikey)
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key_here

# 3. Run
uvicorn main:app --reload
```

API is live at **http://localhost:8000**  
Interactive docs at **http://localhost:8000/docs**

---

## Usage

### POST /predict
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"venue": "Wankhede Stadium, Mumbai"}'
```

### GET /predict (quick test)
```bash
curl "http://localhost:8000/predict?venue=India+Gate+Delhi"
```

---

## Sample Response

```json
{
  "success": true,
  "venue_query": "Wankhede Stadium, Mumbai",
  "data": {
    "venue": {
      "name": "Wankhede Stadium",
      "city": "Mumbai, Maharashtra",
      "type": "stadium",
      "capacity": "33,108",
      "description": "Iconic cricket stadium hosting IPL and international matches."
    },
    "event_context": {
      "likely_event_today": "IPL match — Mumbai Indians vs Kolkata Knight Riders",
      "day_of_week": "Saturday",
      "estimated_attendance": "32,000",
      "weather_note": "Humid, 31°C — slows post-match crowd dispersal"
    },
    "traffic_prediction": {
      "severity": "CRITICAL",
      "congestion_index": 89,
      "confidence": 82,
      "summary": "Severe congestion expected...",
      "peak_period": {
        "start": "21:30",
        "end": "23:30",
        "label": "9:30 PM – 11:30 PM",
        "description": "Post-match exodus — all exits choke simultaneously"
      },
      "pre_surge_starts": "17:30",
      "post_surge_clears": "00:30"
    },
    "impact_zones": [...],
    "alerts": [...],
    "recommendations": {
      "best_arrival_window": "16:00 – 17:00",
      "avoid_roads": ["Marine Drive", "Churchgate flyover"],
      "transit_options": ["Churchgate station (500m)", "Marine Lines station (800m)"]
    }
  }
}
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/predict` | Full prediction — JSON body `{"venue": "..."}` |
| `GET` | `/predict?venue=...` | Same, via query param |
| `GET` | `/health` | Check API key config |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc UI |
