import io
import os
import tempfile
from faster_whisper import WhisperModel

print("Initializing Faster-Whisper model (small, int8)...")
# Initialize the model on first import. 
# We use "small" for speed. compute_type="int8" to save VRAM.
model = WhisperModel("small", device="auto", compute_type="int8")
print("Faster-Whisper initialized.")

def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """
    Transcribe raw audio bytes using Faster-Whisper.
    Uses a temporary file to avoid PyAV memory buffer issues with WebM.
    """
    print(f"Received audio bytes: {len(audio_bytes)} bytes")
    if len(audio_bytes) < 2000:
        print("Audio file too small (likely an empty container). Skipping.")
        return ""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = "".join([segment.text for segment in segments])
        return text.strip()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
