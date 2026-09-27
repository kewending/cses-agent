import os
import json
import httpx
from typing import AsyncGenerator
import asyncio
import re
from services.tts_service import generate_audio_async

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3") # Default to whatever the user uses

def build_parent_prompt(vocabulary: list) -> str:
    vocab_str = ", ".join([v.get('text', '') if isinstance(v, dict) else v for v in vocabulary])
    return f"""You are an English Language Parent. 
Your goal is to have a natural, low-anxiety conversation with me.
RULES:
1. You MUST use simple English. 
2. Try to stick to the following vocabulary words as much as possible (i+1 theory): [{vocab_str}]
3. If I make a grammar or pronunciation mistake, do not scold me or explicitly point it out. Instead, implicitly correct me by naturally repeating my sentence with the correct grammar in your response.
4. Keep your responses short and conversational (1-2 sentences maximum).
5. Ask me follow-up questions to keep the conversation going."""

async def run_parent_chat(history: list, vocabulary: list) -> AsyncGenerator[str, None]:
    system_prompt = build_parent_prompt(vocabulary)
    messages = [{"role": "system", "content": system_prompt}] + history
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": True
        }
        
        try:
            response = await client.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload)
            response.raise_for_status()
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            return
            
        full_content = ""
        current_sentence = ""
        
        delta_and_audio_queue = asyncio.Queue()
        sentence_queue = asyncio.Queue()
        
        async def stream_reader():
            nonlocal full_content, current_sentence
            try:
                async for line in response.aiter_lines():
                    if not line: continue
                    if line.startswith("data: "): line = line[6:]
                    if line == "[DONE]": break
                    try: chunk = json.loads(line)
                    except: continue
                    
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        text = delta["content"]
                        full_content += text
                        current_sentence += text
                        delta_and_audio_queue.put_nowait(("delta", text))
                        
                        # Split by punctuation
                        if re.search(r'[.!?。？！\n]$', current_sentence.strip()):
                            sentence_queue.put_nowait(current_sentence.strip())
                            current_sentence = ""
                            
                if current_sentence.strip():
                    sentence_queue.put_nowait(current_sentence.strip())
            except Exception as e:
                print(f"Stream error: {e}")
            finally:
                sentence_queue.put_nowait(None) # Signal audio worker to stop
                
        async def audio_worker():
            while True:
                sentence = await sentence_queue.get()
                if sentence is None:
                    delta_and_audio_queue.put_nowait(("done", None))
                    break
                # Generate audio for this sentence
                b64_audio = await generate_audio_async(sentence)
                if b64_audio:
                    delta_and_audio_queue.put_nowait(("audio", b64_audio))
                    
        # Start workers
        task1 = asyncio.create_task(stream_reader())
        task2 = asyncio.create_task(audio_worker())
        
        # Consume events and yield to client
        while True:
            event, data = await delta_and_audio_queue.get()
            if event == "done":
                break
            elif event == "delta":
                yield f"event: delta\ndata: {json.dumps({'content': data})}\n\n"
            elif event == "audio":
                yield f"event: audio\ndata: {json.dumps({'base64': data})}\n\n"
                
        await task1
        await task2
        
        # Final text response finished
        yield f"event: done\ndata: {json.dumps({'full_content': full_content})}\n\n"
