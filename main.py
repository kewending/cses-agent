import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import run_agent
from l1_generator import generate_l1_note_stream

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
