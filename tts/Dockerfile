# Tutorly local voice: Chatterbox Multilingual (MIT) on the NVIDIA GPU, falling back to CPU if none is visible.
# Separate image: its torch/numpy pins conflict with Manim's.
FROM python:3.11-slim

# Classic HTTP downloads from Hugging Face (the xet transfer stalled inside containers).
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/models \
    HF_HUB_DISABLE_XET=1 HF_HUB_ENABLE_HF_TRANSFER=0

# CUDA 12.4 build of PyTorch (bundles the CUDA runtime; needs only the host NVIDIA driver).
RUN pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124 \
    && pip install chatterbox-tts==0.1.7 "fastapi>=0.110" "uvicorn>=0.29"

# Bake the model weights into the image so the service starts offline.
RUN python -c "from chatterbox.mtl_tts import ChatterboxMultilingualTTS as M; M.from_pretrained(device='cpu')"

WORKDIR /srv
COPY server.py .
RUN useradd --create-home --uid 10002 tts && chown -R tts /models /srv
USER tts
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
