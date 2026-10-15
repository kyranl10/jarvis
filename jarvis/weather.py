"""Current conditions and today's forecast from Open-Meteo (free, no API key)."""
import requests

# WMO weather codes -> plain words
_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "drizzling", 53: "drizzling", 55: "drizzling heavily",
    61: "lightly raining", 63: "raining", 65: "raining heavily", 71: "lightly snowing",
    73: "snowing", 75: "snowing heavily", 80: "showery", 81: "showery", 82: "pouring",
    95: "stormy", 96: "stormy with hail", 99: "stormy with hail",
}


def forecast(lat: float, lon: float, tz_name: str) -> dict:
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "timezone": tz_name,
            "forecast_days": 1,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    cur, day = data["current"], data["daily"]
    return {
        "temp": round(cur["temperature_2m"]),
        "sky": _CODES.get(cur["weather_code"], "mixed"),
        "high": round(day["temperature_2m_max"][0]),
        "low": round(day["temperature_2m_min"][0]),
        "rain": day["precipitation_probability_max"][0] or 0,
    }
