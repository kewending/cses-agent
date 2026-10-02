import os
import sys
import time

def main():
    print("=" * 60)
    print("CSES Agent - Model Warm-up & Cache Pre-fetching Script")
    print("=" * 60)

    # 1. Hardware & CUDA Check
    print("\n[1/4] Checking Hardware Acceleration...")
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        print(f"  - PyTorch version: {torch.__version__}")
        print(f"  - CUDA available: {cuda_available}")
        if cuda_available:
            print(f"  - GPU Device: {torch.cuda.get_device_name(0)}")
            print(f"  - Device Count: {torch.cuda.device_count()}")
            device = "cuda"
            compute_type = "float16"
        else:
            print("  - Notice: CUDA not active for PyTorch; falling back to CPU.")
            device = "cpu"
            compute_type = "int8"
    except Exception as e:
        print(f"  - Error checking torch: {e}")
        device = "cpu"
        compute_type = "int8"

    # 2. Faster-Whisper ASR Model Pre-fetch
    print("\n[2/4] Initializing Faster-Whisper Small Model...")
    try:
        from faster_whisper import WhisperModel
        print(f"  - Loading WhisperModel('small', device='{device}', compute_type='{compute_type}')...")
        t0 = time.time()
        whisper_model = WhisperModel("small", device=device, compute_type=compute_type)
        print(f"  - Faster-Whisper loaded and cached successfully in {time.time() - t0:.2f}s!")
    except Exception as e:
        print(f"  - Faster-Whisper failed with device='{device}': {e}")
        print("  - Retrying with device='cpu', compute_type='int8'...")
        try:
            from faster_whisper import WhisperModel
            whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            print("  - Faster-Whisper cached successfully on CPU!")
        except Exception as e_cpu:
            print(f"  - Failed to load Faster-Whisper: {e_cpu}")

    # 3. Kokoro TTS Pipelines Pre-fetch
    print("\n[3/4] Initializing Kokoro TTS Pipelines (English & Chinese)...")
    try:
        from kokoro import KPipeline
        print("  - Loading English pipeline ('a')...")
        t0 = time.time()
        pipeline_en = KPipeline(lang_code='a')
        print(f"  - English pipeline ready in {time.time() - t0:.2f}s.")

        print("  - Loading Chinese pipeline ('z')...")
        t0 = time.time()
        pipeline_zh = KPipeline(lang_code='z')
        print(f"  - Chinese pipeline ready in {time.time() - t0:.2f}s.")

        # Test synthesis
        print("  - Testing short synthesis with 'af_heart' voice...")
        generator = pipeline_en("CSES Agent models initialized.", voice="af_heart", speed=1.0)
        audio_chunks = [audio for _, _, audio in generator if audio is not None]
        if audio_chunks:
            print(f"  - Audio synthesis verified ({len(audio_chunks)} chunks generated).")
    except Exception as e:
        print(f"  - Kokoro TTS pipeline initialization encountered an issue: {e}")

    # 4. Ollama LLM Connectivity Check
    print("\n[4/4] Verifying Ollama Local LLM Connection...")
    try:
        import httpx
        from dotenv import load_dotenv
        load_dotenv()
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        print(f"  - Testing Ollama endpoint: {ollama_url} with model: {ollama_model}")
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(ollama_url.replace("/v1", "") + "/api/tags")
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                print(f"  - Ollama is online! Available models: {models}")
                if any(ollama_model in m for m in models):
                    print(f"  - Configured model '{ollama_model}' is available and ready!")
                else:
                    print(f"  - Warning: '{ollama_model}' not found in active tags: {models}")
            else:
                print(f"  - Ollama returned HTTP {resp.status_code}")
    except Exception as e:
        print(f"  - Ollama verification check failed: {e}")

    print("\n" + "=" * 60)
    print("Warm-up complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
