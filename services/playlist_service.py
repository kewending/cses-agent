import json
import httpx
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

async def generate_dynamic_sentence_async(word: str, meaning: str) -> str:
    """
    Generates a single, natural, dynamic example sentence for a given word using the LLM.
    Ensures the sentence is short enough for audio streaming and fits the meaning.
    """
    prompt = f"""You are an English teacher. 
Generate exactly ONE short, natural, everyday English example sentence using the word "{word}".
The meaning of the word in this context is "{meaning}".
The sentence MUST be under 15 words.
Output STRICTLY valid JSON matching this schema:
{{
  "sentence": "The generated sentence here."
}}
Do NOT output anything else. No markdown formatting.
"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
            elif "message" in data:
                content = data["message"]["content"]
            else:
                raise ValueError("Unknown response format from LLM.")
                
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            result = json.loads(content)
            return result.get("sentence", f"I need to learn how to use the word {word}.")
        except Exception as e:
            print(f"Error generating dynamic sentence: {e}")
            return f"I need to learn how to use the word {word}."
