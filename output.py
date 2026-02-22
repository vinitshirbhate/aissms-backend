import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY"),
)

INPUT_PATH = "data/input.json"
OUTPUT_PATH = "data/output.json"

SYSTEM_PROMPT = """
You are a Government-grade AI Traffic Control System for Pune, India.

Your task is to analyze structured traffic state data and produce actionable traffic management decisions.

STRICT RULES:
- Output ONLY valid JSON
- No explanation
- No markdown
- No extra text
- Prioritize safety and congestion reduction
- Consider event impact, weather, congestion, metro proximity, and live traffic
- Use realistic traffic engineering actions
"""

OUTPUT_SCHEMA = """
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

def load_input():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            return data[-1] # Process the latest input
        return data

def generate_decision(data):

    response = client.chat.completions.create(
        model="google/gemini-2.5-flash",
        temperature=0.2,
        max_tokens=900,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""
INPUT TRAFFIC STATE:
{json.dumps(data, indent=2)}

{OUTPUT_SCHEMA}
"""
            }
        ],
    )

    content = response.choices[0].message.content.strip()

    start = content.find("{")
    end = content.rfind("}") + 1
    json_text = content[start:end]

    return json.loads(json_text)

def save_output(output):
    outputs = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                outputs = json.load(f)
                if not isinstance(outputs, list):
                    outputs = [outputs] if outputs else []
        except Exception:
            outputs = []
    
    outputs.append(output)
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=4)

if __name__ == "__main__":

    print("🧠 Generating traffic decision...")

    input_data = load_input()

    decision = generate_decision(input_data)

    save_output(decision)

    print("✅ Output saved to:", OUTPUT_PATH)
    print(json.dumps(decision, indent=4))