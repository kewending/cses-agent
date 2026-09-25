import io
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
import soundfile as sf
from kokoro import KPipeline
import langdetect

# Initialize pipelines at startup (takes ~3s each)
# 'a' for American English, 'z' for Mandarin Chinese
print("Initializing Kokoro TTS Pipelines (EN and ZH)...")
pipeline_en = KPipeline(lang_code='a')
pipeline_zh = KPipeline(lang_code='z')
print("TTS Pipelines Initialized.")

executor = ThreadPoolExecutor(max_workers=2)

def generate_audio_chunk_sync(text: str, voice: str = None, speed: float = 1.0):
    text = text.strip()
    if not text:
        return None
        
    # Detect language
    try:
        lang = langdetect.detect(text)
    except:
        lang = 'en'
        
    if lang.startswith('zh'):
        pipeline = pipeline_zh
        chosen_voice = voice if voice else 'zf_xiaoxiao'
    else:
        pipeline = pipeline_en
        chosen_voice = voice if voice else 'af_heart'
        
    generator = pipeline(text, voice=chosen_voice, speed=speed, split_pattern=r'\n+')
    
    # KPipeline yields (graphemes, phonemes, audio)
    all_audio = []
    for gs, ps, audio in generator:
        if audio is not None:
            all_audio.append(audio)
            
    if not all_audio:
        return None
        
    import numpy as np
    full_audio = np.concatenate(all_audio)
    
    # Write to memory buffer
    buffer = io.BytesIO()
    sf.write(buffer, full_audio, 24000, format='WAV')
    buffer.seek(0)
    
    # Base64 encode
    b64 = base64.b64encode(buffer.read()).decode('utf-8')
    return b64

async def generate_audio_async(text: str, voice: str = None, speed: float = 1.0):
    """
    Non-blocking wrapper for TTS generation.
    """
    loop = asyncio.get_event_loop()
    # Use a lambda to pass the kwargs correctly, or use partial
    from functools import partial
    return await loop.run_in_executor(executor, partial(generate_audio_chunk_sync, text, voice=voice, speed=speed))
