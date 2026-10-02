import json
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

async def generate_drills_async(vocab_list: list, drill_type: str = "substitution", count: int = 5) -> dict:
    """
    Generates a list of pattern drills using the provided vocabulary.
    Returns a dictionary with a 'drills' key containing a list of drill objects.
    """
    if not vocab_list:
        vocab_list = ["apple", "run", "happy", "beautiful", "quickly"] # fallback
        
    vocab_str = ", ".join(vocab_list)
    
    if drill_type == "substitution":
        prompt = f"""You are an English linguistic expert designing a "Substitution Drill" (Pattern Drill) for an English learner.
I will give you a list of words. You must generate exactly {count} drill questions.
For each question, select one word from the list as the 'cue'. 
Create a simple, natural 'base_sentence' that DOES NOT contain the cue, but contains a word that can be logically replaced by the cue.
Then create the 'expected_response' where the replaceable word is swapped with the cue, modifying grammar if absolutely necessary.

Vocabulary list: [{vocab_str}]

Output strictly valid JSON matching this schema:
{{
  "drills": [
    {{
      "base_sentence": "I usually sleep when I feel tired.",
      "cue": "exhausted",
      "expected_response": "I usually sleep when I feel exhausted.",
      "type": "substitution"
    }}
  ]
}}
"""
    elif drill_type == "transformation":
        prompt = f"""You are an English linguistic expert designing a "Transformation Drill".
I will give you a list of words. Generate exactly {count} drill questions using these words in the sentences.
For each question, provide a simple 'base_sentence'. The 'cue' should be a grammar instruction like "Past Tense", "Negative", "Question", or "Plural".
The 'expected_response' must be the base_sentence transformed according to the cue.

Vocabulary list: [{vocab_str}]

Output strictly valid JSON matching this schema:
{{
  "drills": [
    {{
      "base_sentence": "She eats an apple.",
      "cue": "Past Tense",
      "expected_response": "She ate an apple.",
      "type": "transformation"
    }}
  ]
}}
"""
    else:
        raise ValueError(f"Unknown drill_type: {drill_type}")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json" # Forces Ollama to output valid JSON
    }
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            response = await client.post(f"{OLLAMA_BASE_URL}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Handle OpenAI compatible response format
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
            
            drills_json = json.loads(content)
            return drills_json
        except Exception as e:
            print(f"Error generating drills: {e}")
            print(f"Raw response data: {data if 'data' in locals() else 'None'}")
            return {"drills": []}
