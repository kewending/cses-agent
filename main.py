import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import run_agent
from services.summary_service import generate_l1_note_stream

app = FastAPI(title="CSES Agent Harness")

# Enable CORS so Next.js dashboard can communicate with the agent
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    messages: list[dict]

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Returns an SSE stream.
    Events: tool_start, tool_end, delta, done, error
    """
    print(req.messages)
    return StreamingResponse(run_agent(req.messages), media_type="text/event-stream")

class L1NoteRequest(BaseModel):
    url: str

@app.post("/api/l1-note")
async def l1_note_endpoint(req: L1NoteRequest):
    """
    Returns an SSE stream for generating an L1 Note from a URL.
    """
    print(f"Generating L1 Note for URL: {req.url}")
    return StreamingResponse(generate_l1_note_stream(req.url), media_type="text/event-stream")

import os
from fastapi.staticfiles import StaticFiles
from fastapi import BackgroundTasks

# Serve reports directory for audio playback
reports_dir = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(reports_dir, exist_ok=True)
app.mount("/reports", StaticFiles(directory=reports_dir), name="reports")

@app.get("/api/daily-report")
def get_daily_report():
    """
    Endpoint for the frontend to manually trigger or fetch today's daily report.
    Returns the paths to the audio and script files.
    """
    from services.report_service import get_or_create_daily_report
    result = get_or_create_daily_report()
    if result.get("status") == "error":
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    # Return relative URLs for the frontend
    filename = os.path.basename(result["audio_file"])
    return {
        "status": result["status"],
        "audio_url": f"/reports/{filename}",
        "script_url": f"/reports/{filename.replace('.wav', '.txt')}"
    }

class TTSRequest(BaseModel):
    text: str
    voice: str | None = None
    speed: float = 1.0

@app.post("/api/tts")
async def tts_endpoint(req: TTSRequest):
    from services.tts_service import generate_audio_async
    b64_audio = await generate_audio_async(req.text, voice=req.voice, speed=req.speed)
    if not b64_audio:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Could not generate audio")
    return {"audio_base64": b64_audio}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
