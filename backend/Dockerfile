# Tutorly backend: FastAPI + Gemini SDK + SymPy + NetworkX + Manim (FFmpeg, LaTeX).
# Build context is the repository root (so the shared prompts/ directory can be copied).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies for Manim: cairo/pango (+ headers in case wheels are missing),
# FFmpeg, and a LaTeX subset sufficient for MathTex/Tex (standalone, amsmath, dvisvgm).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config \
    libcairo2-dev libpango1.0-dev \
    ffmpeg \
    texlive-latex-base texlive-latex-recommended texlive-latex-extra \
    texlive-fonts-recommended texlive-science \
    dvisvgm \
    fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY backend/pyproject.toml ./pyproject.toml
RUN mkdir -p app && touch app/__init__.py \
    && pip install ".[dev]" \
    && rm -rf app build *.egg-info

# Offline neural fallback voices (Piper), used when Azure or the local neural service is unavailable.
ARG PIPER_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0
RUN mkdir -p /opt/piper && python - <<'EOF'
import os, urllib.request
base = os.environ.get("PIPER_BASE", "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0")
for path in ("pl/pl_PL/gosia/medium/pl_PL-gosia-medium", "en/en_US/lessac/medium/en_US-lessac-medium"):
    name = path.rsplit("/", 1)[1]
    for ext in (".onnx", ".onnx.json"):
        urllib.request.urlretrieve(f"{base}/{path}{ext}", f"/opt/piper/{name}{ext}")
print(sorted(os.listdir("/opt/piper")))
EOF

COPY backend/app ./app
COPY backend/tests ./tests
COPY prompts ./prompts

# Run as an unprivileged user; generated Manim code inherits these restrictions.
RUN useradd --create-home --uid 10001 mathlens \
    && mkdir -p /data \
    && chown -R mathlens:mathlens /data /app
USER mathlens

ENV DATA_DIR=/data \
    PROMPTS_DIR=/app/prompts \
    PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
