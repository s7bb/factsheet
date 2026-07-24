# Deterministic PDF factsheet builder (no LLM).
# Base image ships Chromium + all system libs for Playwright, matching the
# playwright version pinned below.
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

# Python deps (pandas + playwright). Browser is already in the base image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Generator only; data is fetched at runtime from raw.githubusercontent.com.
COPY generate.py ./

# PDFs land here; mount a host dir over it to collect the output.
RUN mkdir -p /app/output
VOLUME ["/app/output"]

# Args (e.g. --month 2026-06) pass straight through to the generator.
ENTRYPOINT ["python", "generate.py"]
