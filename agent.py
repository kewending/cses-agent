import os
import json
import httpx
from typing import AsyncGenerator
from tools.sql_tools import get_database_schema, execute_sql_query
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "granite4.2:3b")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "Returns the DDL/Schema structure of the requested tables. Use this before writing SQL to understand column names and relationships.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of table names to retrieve the schema for. Leave empty to get all tables."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "Executes a SQL query on the SQLite database. Only SELECT and INSERT are allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are CSES Agent, an intelligent workflow assistant for a Life OS dashboard.
Your goal is to help the user query their data, insert data, and analyze data.
You have access to a local SQLite database.
ALWAYS follow these steps when asked about data:
1. If you don't know the schema, call `get_database_schema` to discover the exact table structures.
2. Call `execute_sql_query` to read (SELECT) or write (INSERT) data. Do NOT use UPDATE or DELETE.
3. If your SQL query fails (e.g. syntax error or foreign key error), read the error message, correct your SQL, and try again.
4. Once you have the data, provide a clear, concise, and helpful Markdown response to the user.
"""

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
                "tools": TOOLS,
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
                        
                    result = ""
                    if func_name == "get_database_schema":
                        result = get_database_schema(args.get("tables"))
                    elif func_name == "execute_sql_query":
                        result = execute_sql_query(args.get("query"))
                    else:
                        result = f"Error: Unknown function {func_name}"
                        
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
