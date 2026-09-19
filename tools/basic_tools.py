from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import json
from config import TIMEZONE, DEFAULT_LAT, DEFAULT_LON
from tools.registry import registry
from pydantic import BaseModel

class GetCurrentTimeArgs(BaseModel):
    pass # No arguments needed for this tool

@registry.register(args_schema=GetCurrentTimeArgs)
def get_current_time() -> str:
    """
    Returns the current local time.
    Use this when the user asks about the current time or date or day of week.
    """
    now = datetime.now(ZoneInfo(TIMEZONE))

    return (
        f"{now.isoformat()} | "
        f"{now.strftime('%A')} | "
        f"Timezone: {now.tzname()} | "
        f"UTC Offset: {now.strftime('%z')}"
    )

class GetWeatherArgs(BaseModel):
    pass # No arguments needed, uses default lat/lon

@registry.register(args_schema=GetWeatherArgs)
def get_weather() -> str:
    """
    Returns the current weather forecast for today, including high/low temps, sunrise, and sunset.
    Use this when the user asks about the weather today.
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={DEFAULT_LAT}&longitude={DEFAULT_LON}&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset&timezone=auto&forecast_days=1"
    
    weather_codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Rime fog", 51: "Light drizzle", 61: "Slight rain", 
        63: "Moderate rain", 65: "Heavy rain", 95: "Thunderstorm"
    }
    
    try:
        response = httpx.get(url)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily")
        
        if not daily:
            return json.dumps({"error": "No daily data returned from Open-Meteo"})
            
        weather_code = daily["weather_code"][0]
        
        weather_context = {
            "weather": weather_codes.get(weather_code, "Unknown"),
            "high": daily["temperature_2m_max"][0],
            "low": daily["temperature_2m_min"][0],
            "sunrise": daily["sunrise"][0].split("T")[1],
            "sunset": daily["sunset"][0].split("T")[1],
        }
        
        return json.dumps(weather_context)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch weather: {str(e)}"})
