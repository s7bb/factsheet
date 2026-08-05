# Deterministic PDF factsheet builder (no LLM).
# Base image ships Chromium + all system libs for Playwright, matching the
# playwright version pinned below.
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

# Python deps (pandas + playwright). Browser is already in the base image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Generatoren; Daten werden zur Laufzeit von raw.githubusercontent.com geholt.
COPY generate.py schulweg.py ./

# PDFs land here; mount a host dir over it to collect the output.
RUN mkdir -p /app/output
VOLUME ["/app/output"]

# Ohne Argumente laufen beide Generatoren; mit Argumenten (z. B. --month
# 2026-06) werden sie an beide durchgereicht.
ENTRYPOINT ["sh", "-c", "python generate.py \"$@\" && python schulweg.py \"$@\"", "--"]
