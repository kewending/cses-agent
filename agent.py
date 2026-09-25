import os
import json
import httpx
from typing import AsyncGenerator
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_BASE_URL or not OLLAMA_MODEL:
    raise ValueError("Please set OLLAMA_BASE_URL and OLLAMA_MODEL in your .env file")

from prompts import SYSTEM_PROMPT
from tools.registry import registry

# Make sure tools are imported so they register themselves
import tools.sql_tools
import tools.basic_tools

from services.tts_service import generate_audio_async
import asyncio
import re

async def run_agent(history: list) -> AsyncGenerator[str, None]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            payload = {
                "model": OLLAMA_MODEL,
                "messages": messages,
                "tools": registry.get_schemas(),
                "stream": True
            }
            
            try:
                # We use stream here
                response = await client.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload)
                response.raise_for_status()
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                break
                
            is_tool_call = False
            accumulated_tool_calls = []
            full_content = ""
            current_sentence = ""
            
            event_queue = asyncio.Queue()
            
            async def stream_reader():
                nonlocal is_tool_call, full_content, current_sentence, accumulated_tool_calls
                try:
                    async for line in response.aiter_lines():
                        if not line: continue
                        if line.startswith("data: "):
                            line = line[6:]
                        if line == "[DONE]":
                            break
                            
                        try:
                            chunk = json.loads(line)
                        except:
                            continue
                            
                        delta = chunk["choices"][0].get("delta", {})
                        
                        if "tool_calls" in delta:
                            is_tool_call = True
                            for tc in delta["tool_calls"]:
                                idx = tc["index"]
                                while len(accumulated_tool_calls) <= idx:
                                    accumulated_tool_calls.append({"id": tc.get("id", f"call_{idx}"), "type": "function", "function": {"name": "", "arguments": ""}})
                                if "function" in tc:
                                    if "name" in tc["function"] and tc["function"]["name"]:
                                        accumulated_tool_calls[idx]["function"]["name"] += tc["function"]["name"]
                                    if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                        accumulated_tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]
                                        
                        if not is_tool_call and "content" in delta and delta["content"]:
                            text = delta["content"]
                            full_content += text
                            current_sentence += text
                            event_queue.put_nowait(("delta", text))
                            
                            if re.search(r'[.!?。？！\n]$', current_sentence.strip()):
                                event_queue.put_nowait(("sentence", current_sentence.strip()))
                                current_sentence = ""
                                
                    if current_sentence.strip() and not is_tool_call:
                        event_queue.put_nowait(("sentence", current_sentence.strip()))
                except Exception as e:
                    print(f"Stream error: {e}")
                finally:
                    event_queue.put_nowait(("stream_done", None))
                    
            async def audio_worker():
                while True:
                    event, data = await event_queue.get()
                    if event == "stream_done":
                        event_queue.put_nowait(("audio_done", None))
                        break
                    elif event == "sentence":
                        b64_audio = await generate_audio_async(data)
                        if b64_audio:
                            event_queue.put_nowait(("audio", b64_audio))
                    else:
                        # re-queue delta events so they can be yielded by the main loop
                        # Wait, queue is FIFO, re-queueing will mess up order if we have multiple workers.
                        pass # handled below by a single consumer!
                        
            # Wait, a single queue where stream_reader puts delta/sentence, and audio_worker takes sentence and puts audio.
            # But if main loop gets from queue, it will steal 'sentence' from audio_worker!
            # Let's use TWO queues.
            
            delta_and_audio_queue = asyncio.Queue()
            sentence_queue = asyncio.Queue()
            
            async def stream_reader_2():
                nonlocal is_tool_call, full_content, current_sentence, accumulated_tool_calls
                try:
                    async for line in response.aiter_lines():
                        if not line: continue
                        if line.startswith("data: "): line = line[6:]
                        if line == "[DONE]": break
                        try: chunk = json.loads(line)
                        except: continue
                        
                        delta = chunk["choices"][0].get("delta", {})
                        if "tool_calls" in delta:
                            is_tool_call = True
                            for tc in delta["tool_calls"]:
                                idx = tc["index"]
                                while len(accumulated_tool_calls) <= idx:
                                    accumulated_tool_calls.append({"id": tc.get("id", f"call_{idx}"), "type": "function", "function": {"name": "", "arguments": ""}})
                                if "function" in tc:
                                    if "name" in tc["function"] and tc["function"]["name"]:
                                        accumulated_tool_calls[idx]["function"]["name"] += tc["function"]["name"]
                                    if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                        accumulated_tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]
                                        
                        if not is_tool_call and "content" in delta and delta["content"]:
                            text = delta["content"]
                            full_content += text
                            current_sentence += text
                            delta_and_audio_queue.put_nowait(("delta", text))
                            
                            if re.search(r'[.!?。？！\n]$', current_sentence.strip()):
                                sentence_queue.put_nowait(current_sentence.strip())
                                current_sentence = ""
                                
                    if current_sentence.strip() and not is_tool_call:
                        sentence_queue.put_nowait(current_sentence.strip())
                except Exception as e:
                    print(f"Stream error: {e}")
                finally:
                    sentence_queue.put_nowait(None) # Signal audio worker to stop
                    
            async def audio_worker_2():
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is None:
                        delta_and_audio_queue.put_nowait(("done", None))
                        break
                    b64_audio = await generate_audio_async(sentence)
                    if b64_audio:
                        delta_and_audio_queue.put_nowait(("audio", b64_audio))
                        
            # Start workers
            task1 = asyncio.create_task(stream_reader_2())
            task2 = asyncio.create_task(audio_worker_2())
            
            # Consume events
            while True:
                if is_tool_call and task1.done():
                    # If it's a tool call, we don't wait for audio_worker, it won't produce anything
                    # Actually, sentence_queue will get None, so audio_worker will finish and put "done"
                    pass
                    
                event, data = await delta_and_audio_queue.get()
                if event == "done":
                    break
                elif event == "delta":
                    yield f"event: delta\ndata: {json.dumps({'content': data})}\n\n"
                elif event == "audio":
                    yield f"event: audio\ndata: {json.dumps({'base64': data})}\n\n"
                    
            await task1
            await task2
            
            if is_tool_call:
                # Handle tool calls
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": accumulated_tool_calls
                })
                
                for tool_call in accumulated_tool_calls:
                    func_name = tool_call["function"]["name"]
                    try: args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError: args = {}
                        
                    yield f"event: tool_start\ndata: {json.dumps({'name': func_name, 'args': args})}\n\n"
                    result = registry.call_tool(func_name, args)
                    
                    display_result = str(result)
                    if len(display_result) > 200: display_result = display_result[:200] + "..."
                    yield f"event: tool_end\ndata: {json.dumps({'name': func_name, 'result': display_result})}\n\n"
                    
                    messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": str(result),
                        "tool_call_id": tool_call["id"]
                    })
            else:
                # Final text response finished
                messages.append({"role": "assistant", "content": full_content})
                yield f"event: done\ndata: {{}}\n\n"
                break
