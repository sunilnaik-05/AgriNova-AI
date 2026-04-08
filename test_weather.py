import requests

def get_weather(location: str):
    WMO_CODES = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Heavy drizzle",
        61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
        80: "Light rain showers", 81: "Moderate rain showers", 82: "Heavy rain showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail",
    }
    try:
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(location)}&count=5&language=en&format=json"
        )
        geo_data = requests.get(geo_url, timeout=8).json()
        if "results" not in geo_data or not geo_data["results"]:
            return {"error": f"Location '{location}' not found."}

        r = geo_data["results"][0]
        for res in geo_data["results"]:
            if res.get("country_code") == "IN":
                r = res
                break

        lat, lon = r["latitude"], r["longitude"]
        place_name = r.get("name", location)
        admin1 = r.get("admin1", "")
        country = r.get("country", "")

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&hourly=relative_humidity_2m,apparent_temperature,precipitation_probability"
            f"&timezone=Asia%2FKolkata&forecast_days=1"
        )
        w_data = requests.get(weather_url, timeout=8).json()
        if "current_weather" not in w_data:
            return {"error": "Weather data unavailable."}

        cw = w_data["current_weather"]
        hourly = w_data.get("hourly", {})

        return {
            "location": f"{place_name}, {admin1}, {country}".strip(", "),
            "temperature_celsius": cw.get("temperature"),
            "feels_like_celsius": hourly.get("apparent_temperature", [None])[0],
            "condition": WMO_CODES.get(cw.get("weathercode", 0), "Unknown"),
            "windspeed_kmh": cw.get("windspeed"),
            "humidity_percent": hourly.get("relative_humidity_2m", [None])[0],
            "rain_probability_percent": hourly.get("precipitation_probability", [None])[0],
            "status": "Live weather data."
        }
    except Exception as e:
        return {"error": str(e)}

# Test multiple locations
for loc in ["Haveri", "Koppal", "Yadgir", "Bhopal", "Delhi", "Raichur"]:
    result = get_weather(loc)
    print(f"\n=== {loc} ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
