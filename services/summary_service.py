import sys
import os
import json
import httpx
import asyncio
from typing import AsyncGenerator
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

SYSTEM_PROMPT = """You are an expert at summarizing web content into structured L1 Notes.
Given the markdown content of a webpage, you must extract the key information and structure it into the following format:

## Summary
(A brief paragraph summarizing the entire content)

## Key Takeaways
- (Bullet point 1)
- (Bullet point 2)
- ...

## Action Items
- [ ] (Action item 1)
- [ ] (Action item 2)
- ...

Only output the structured markdown. Do not include introductory text like "Here is the summary:"."""

def _crawl_sync(url: str) -> str:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    async def _do_crawl():
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            return result.markdown

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_do_crawl())
    finally:
        loop.close()

async def generate_l1_note_stream(url: str) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'status': 'crawling'})}\n\n"
    
    try:
        markdown_content = await asyncio.to_thread(_crawl_sync, url)
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': f'Failed to crawl URL: {str(e)}'})}\n\n"
        return

    if not markdown_content:
        yield f"event: error\ndata: {json.dumps({'error': 'No content could be extracted from the URL.'})}\n\n"
        return

    # Truncate extremely long markdown to avoid exceeding context window (assuming ~8k context)
    # 25000 characters is roughly 6000-7000 tokens
    if len(markdown_content) > 25000:
        markdown_content = markdown_content[:25000] + "\n...[Content truncated due to length]..."

    yield f"data: {json.dumps({'status': 'summarizing'})}\n\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Please summarize the following content:\n\n{markdown_content}"}
    ]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{OLLAMA_BASE_URL}/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    content = delta["content"]
                                    if content:
                                        yield f"event: delta\ndata: {json.dumps({'content': content})}\n\n"
                        except json.JSONDecodeError:
                            continue
                
        yield f"event: done\ndata: {{}}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': f'LLM generation failed: {str(e)}'})}\n\n"
