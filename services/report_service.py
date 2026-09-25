import os
import json
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from config import TIMEZONE
from tools.basic_tools import get_weather
from services.tts_service import generate_audio_chunk_sync
import base64

from dotenv import load_dotenv
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def fetch_news() -> str:
    """
    Fetches news from Free News API for specific topics.
    """
    api_key = os.getenv("FREE_NEWS_API")
    if not api_key:
        return json.dumps({"error": "Free News API key is missing or invalid."})
    
    import datetime as dt
    from zoneinfo import ZoneInfo
    # Fetch news from the last 24 hours
    yesterday = (dt.datetime.now(ZoneInfo("UTC")) - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    url = "https://api.freenewsapi.io/v1/news"
    headers = {
        "x-api-key": api_key
    }

    feeds = {
        "Ballarat Local News": {
            "params": {"in_title": "Ballarat", "published_after": yesterday}
        },
        "Australia": {
            "params": {"country": "au", "published_after": yesterday}
        },
        "World": {
            "params": {"topic": "world", "published_after": yesterday}
        },
        "Business": {
            "params": {"topic": "business", "published_after": yesterday}
        },
        "Technology": {
            "params": {"topic": "technology", "published_after": yesterday}
        },
        "China": {
            "params": {"country": "cn", "published_after": yesterday}
        }
    }

    all_news_md = []

    try:
        with httpx.Client(timeout=15.0) as client:
            for section, payload in feeds.items():
                params = payload["params"]
                response = client.get(url, headers=headers, params=params)
                
                all_news_md.append(f"# {section}")
                
                if response.status_code == 200:
                    data = response.json()
                    articles = data.get("data", [])
                    
                    if not articles:
                        all_news_md.append("No news available.\n")
                        continue
                        
                    # Top 5 articles per section
                    for idx, article in enumerate(articles[:5]):
                        title = article.get("title", "No Title")
                        uuid = article.get("uuid")
                        publisher = article.get("publisher", "")
                        
                        body = ""
                        if uuid:
                            details_url = "https://api.freenewsapi.io/v1/details"
                            details_response = client.get(details_url, headers=headers, params={"uuid": uuid})
                            if details_response.status_code == 200:
                                detail_data = details_response.json().get("data", {})
                                body = detail_data.get("body", "")
                        
                        title_line = f"{idx+1}. {title}"
                        if publisher:
                            title_line += f" (Published by {publisher})"
                        all_news_md.append(title_line)
                        
                        if body:
                            all_news_md.append(body)
                    all_news_md.append("") # Empty line between sections
                else:
                    all_news_md.append(f"Error fetching news (Status {response.status_code})\n")
                    
        md_content = "\n".join(all_news_md)
        
        # Save to file
        today_str = dt.datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")
        news_file = os.path.join(REPORTS_DIR, f"news_{today_str}.md")
        with open(news_file, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        return md_content
    except Exception as e:
        return f"Error fetching news: {str(e)}"

def generate_daily_report_script(weather_data: str, news_data: str) -> str:
    """
    Uses the local LLM to synthesize weather and news into a script, processing section by section.
    """
    def call_llm(sys_prompt: str, usr_prompt: str) -> str:
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": usr_prompt}
            ],
            "stream": False
        }
        response = httpx.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload, timeout=600.0)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
        
    try:
        final_script_parts = []
        
        # 1. Weather Segment
        weather_system = (
            "You are a professional radio news anchor. Write the opening of the daily news script, "
            "welcoming the listeners and giving a smooth, engaging summary of today's weather. "
            "Do not include any conversational filler at the start like 'Here is your script'. "
            "Do NOT use any markdown formatting, asterisks (*), hashtags, or special characters. "
            "Write the script in English."
        )
        weather_user = f"Today's Weather Data:\n{weather_data}"
        print("Generating weather script segment...")
        weather_script = call_llm(weather_system, weather_user)
        final_script_parts.append(weather_script)
        
        # 2. News Segments
        sections = ("\n" + news_data).split("\n# ")
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            lines = section.split("\n", 1)
            section_name = lines[0].strip()
            section_content = lines[1].strip() if len(lines) > 1 else ""
            
            if "No news available" in section_content or not section_content:
                print(f"Skipping {section_name}, no news.")
                continue
                
            print(f"Generating script for {section_name}...")
            news_system = (
                f"You are a professional radio news anchor. Your task is to write a news script segment for the '{section_name}' section. "
                "Use a natural transition phrase at the beginning (e.g., 'Now let's take a look at the news from...'). "
                "Summarize the provided news stories smoothly. "
                "Do not include any conversational filler at the start like 'Here is your script'. "
                "Do NOT use any markdown formatting, asterisks (*), hashtags, or special characters. "
                "Write the script in English."
            )
            news_user = f"Stories for {section_name}:\n{section_content}"
            section_script = call_llm(news_system, news_user)
            final_script_parts.append(section_script)
            
        # 3. Final Sign-off
        final_script_parts.append("That's all for today's report. Thanks for listening, and have a great day!")
        
        return "\n\n".join(final_script_parts)
    except Exception as e:
        return f"Error generating script: {str(e)}"

def get_or_create_daily_report():
    """
    Checks if today's report exists. If not, fetches data, writes script, creates TTS audio, and saves it.
    Returns the path to the audio file and the text script.
    """
    today_str = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    txt_path = os.path.join(REPORTS_DIR, f"{today_str}.txt")
    wav_path = os.path.join(REPORTS_DIR, f"{today_str}.wav")

    if os.path.exists(txt_path) and os.path.exists(wav_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            script = f.read()
        return {"status": "cached", "script": script, "audio_file": wav_path, "text_file": txt_path}

    # 1. Fetch data
    weather_data = get_weather()
    news_data = fetch_news()

    # 2. Generate script
    script = generate_daily_report_script(weather_data, news_data)

    if script.startswith("Error generating script"):
        return {"status": "error", "message": script}

    # 3. Generate Audio
    print("Generating TTS for Daily Report...")
    b64_audio = generate_audio_chunk_sync(script)
    
    if not b64_audio:
        return {"status": "error", "message": "Failed to generate audio from script."}

    # 4. Save to files
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(script)
        
    audio_bytes = base64.b64decode(b64_audio)
    with open(wav_path, "wb") as f:
        f.write(audio_bytes)

    return {"status": "created", "script": script, "audio_file": wav_path, "text_file": txt_path}
