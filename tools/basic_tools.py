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
    Returns the current weather forecast for today, including high/low temps, current conditions, sunrise, and sunset.
    Use this when the user asks about the weather today or for the daily report.
    """
    import os
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    today_str = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    weather_cache_file = os.path.join(reports_dir, f"weather_{today_str}.json")
    
    if os.path.exists(weather_cache_file):
        with open(weather_cache_file, "r", encoding="utf-8") as f:
            return f.read()

    url = f"https://api.open-meteo.com/v1/forecast?latitude={DEFAULT_LAT}&longitude={DEFAULT_LON}&daily=weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,sunrise,sunset,precipitation_probability_max&current=temperature_2m,weather_code,precipitation&timezone=auto&forecast_days=1"
    # WMO Weather interpretation codes (WMO)
    weather_codes = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain", 66: "Light freezing rain", 67: "Heavy freezing rain",
	71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall", 77: "Snow grains",
	80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
	85: "Slight snow showers", 86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with slight hail",
	97: "Heavy thunderstorm", 99: "Thunderstorm with heavy hail"
    }
    
    try:
        response = httpx.get(url)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily")
        current = data.get("current")
        
        if not daily or not current:
            return json.dumps({"error": "No data returned from Open-Meteo"})
            
        daily_weather_code = daily["weather_code"][0]
        current_weather_code = current["weather_code"]
        
        weather_context = {
            "current": {
                "temperature": current["temperature_2m"],
                "precipitation_mm": current["precipitation"],
                "condition": weather_codes.get(current_weather_code, "Unknown")
            },
            "daily": {
                "condition": weather_codes.get(daily_weather_code, "Unknown"),
                "high": daily["temperature_2m_max"][0],
                "low": daily["temperature_2m_min"][0],
                "uv_index_max": daily.get("uv_index_max", [None])[0],
                "precipitation_probability_max": daily.get("precipitation_probability_max", [None])[0],
                "sunrise": daily["sunrise"][0].split("T")[1],
                "sunset": daily["sunset"][0].split("T")[1],
            }
        }
        
        result_str = json.dumps(weather_context)
        with open(weather_cache_file, "w", encoding="utf-8") as f:
            f.write(result_str)
            
        return result_str
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch weather: {str(e)}"})

class PlayDailyReportArgs(BaseModel):
    pass # No arguments needed

@registry.register(args_schema=PlayDailyReportArgs)
def play_daily_report() -> str:
    """
    Generates (if not cached) and returns the daily news and weather report.
    Use this when the user asks for their daily report, news update, or morning briefing.
    """
    import sys
    import os
    # Ensure root is in sys.path to import services
    root_dir = os.path.dirname(os.path.dirname(__file__))
    if root_dir not in sys.path:
        sys.path.append(root_dir)
        
    try:
        from services.report_service import get_or_create_daily_report
        result = get_or_create_daily_report()
        
        if result.get("status") == "error":
            return json.dumps({"error": result.get("message", "Unknown error generating report")})
            
        script = result.get("script", "")
        # Return a short success message so the agent can summarize it,
        # but also provide the script if the agent wants to read it.
        return json.dumps({
            "message": "Daily report generated and TTS audio saved successfully.",
            "audio_file": result.get("audio_file"),
            "text_file": result.get("text_file"),
            "script_preview": script[:300] + "..." # Give agent a preview
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to play daily report: {str(e)}"})
