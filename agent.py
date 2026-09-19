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

async def run_agent(history: list) -> AsyncGenerator[str, None]:
    # Ensure system prompt is first
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    # We use a long timeout since local models might take time to generate SQL or final response
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            # 1. Send conversation to model
            payload = {
                "model": OLLAMA_MODEL,
                "messages": messages,
                "tools": registry.get_schemas(),
                "stream": False
            }
            
            try:
                response = await client.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload)
                response.raise_for_status()
                response_data = response.json()
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                break
            
            message = response_data['choices'][0]['message']
            messages.append(message)
            
            # 2. Check if the model wants to call tools
            if "tool_calls" in message and message["tool_calls"]:
                tool_calls = message["tool_calls"]
                
                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                        
                    yield f"event: tool_start\ndata: {json.dumps({'name': func_name, 'args': args})}\n\n"
                        
                    result = registry.call_tool(func_name, args)
                        
                    # Truncate result for frontend display only, full result goes to model
                    display_result = str(result)
                    if len(display_result) > 200:
                        display_result = display_result[:200] + "..."
                        
                    yield f"event: tool_end\ndata: {json.dumps({'name': func_name, 'result': display_result})}\n\n"
                    
                    # 3. Append tool result for the model's next turn
                    messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": str(result),
                        "tool_call_id": tool_call["id"]
                    })
                
                # Loop will continue and send the tool results back to the model
            else:
                # No tool calls, this is the final response. 
                # We yield the final text in chunks.
                content = message.get("content", "")

                print(f"LLM reply: {content}", flush=True)
                
                chunk_size = 10
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i+chunk_size]
                    yield f"event: delta\ndata: {json.dumps({'content': chunk})}\n\n"
                    
                yield f"event: done\ndata: {{}}\n\n"
                break
