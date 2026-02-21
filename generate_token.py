import os
import requests
from dotenv import load_dotenv

# 🔐 Load environment variables
load_dotenv()

MAPPLS_CLIENT_ID = os.getenv("MAPPLS_CLIENT_ID")
MAPPLS_CLIENT_SECRET = os.getenv("MAPPLS_CLIENT_SECRET")


# =====================================================
# ⭐ STEP 1 — Get OAuth Token
# =====================================================

def get_mappls_token():
    url = "https://outpost.mappls.com/api/security/oauth/token"

    payload = {
        "grant_type": "client_credentials",
        "client_id": MAPPLS_CLIENT_ID,
        "client_secret": MAPPLS_CLIENT_SECRET,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(
            url,
            data=payload,
            headers=headers,
            timeout=10,
        )

        print("\n🔐 Token Request Status:", response.status_code)

        data = response.json()

        if "access_token" not in data:
            print("❌ Failed to get token")
            print("Response:", data)
            return None

        token = data["access_token"]

        print("✅ Access Token obtained")

        return token

    except Exception as e:
        print("❌ Token request failed:", str(e))
        return None


# =====================================================
# ⭐ STEP 2 — Fetch Traffic Data
# =====================================================

def fetch_mappls_traffic(lat: float, lon: float):
    token = get_mappls_token()

    if not token:
        return

    # Create nearby destination to analyze congestion
    # IMPORTANT: Mappls uses LON,LAT order
    dest_lat = lat + 0.02
    dest_lon = lon + 0.02

    # Correct URL format: https://apis.mappls.com/advancedmaps/v1/{token}/route_adv/driving/{start_lon},{start_lat};{dest_lon},{dest_lat}
    url = f"https://apis.mappls.com/advancedmaps/v1/{token}/route_adv/driving/{lon},{lat};{dest_lon},{dest_lat}"

    params = {
        "traffic": "true",
        "steps": "false",
        "resource": "route_eta" # Ensures traffic-aware calculation
    }

    try:
        response = requests.get(url, params=params, timeout=10)

        print("\n🚦 Traffic API Status:", response.status_code)
        
        data = response.json()

        if response.status_code != 200:
            print("❌ API Error:", data)
            return

        routes = data.get("routes", [])

        if not routes:
            print("❌ No route data found")
            print(data)
            return

        route = routes[0]

        distance_km = route.get("distance", 0) / 1000
        duration_min = route.get("duration", 0) / 60
        # If 'duration_without_traffic' is available, use it to calculate delay
        # Otherwise, assume trafficDelay exists or default to 0
        duration_no_traffic = route.get("duration_without_traffic", route.get("duration", 0)) / 60
        delay_min = max(0, duration_min - duration_no_traffic)

        avg_speed = distance_km / (duration_min / 60) if duration_min else 0

        # Congestion classification
        if delay_min > 10:
            congestion = "CRITICAL"
        elif delay_min > 5:
            congestion = "HIGH"
        elif delay_min > 2:
            congestion = "MODERATE"
        else:
            congestion = "LOW"

        print("\n📊 TRAFFIC ANALYSIS RESULT")
        print("--------------------------------")
        print("Distance (km):", round(distance_km, 2))
        print("Travel Time (min):", round(duration_min, 1))
        print("Traffic Delay (min):", round(delay_min, 1))
        print("Average Speed (km/h):", round(avg_speed, 1))
        print("Congestion Level:", congestion)

        return {
            "distance_km": round(distance_km, 2),
            "travel_time_min": round(duration_min, 1),
            "traffic_delay_min": round(delay_min, 1),
            "average_speed_kmh": round(avg_speed, 1),
            "congestion_level": congestion
        }

    except Exception as e:
        print("❌ Traffic fetch failed:", str(e))
        return {
            "error": str(e),
            "congestion_level": "UNKNOWN"
        }


# =====================================================
# ⭐ STEP 3 — RUN SCRIPT
# =====================================================

if __name__ == "__main__":

    print("🏙️ Mappls Traffic Data Fetcher")

    # Pune Shivajinagar coordinates
    latitude = 18.5308
    longitude = 73.8470

    fetch_mappls_traffic(latitude, longitude)