from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import run_agent

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
