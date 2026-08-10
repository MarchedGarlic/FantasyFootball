# Fantasy Football Analysis - container image for Azure App Service (Linux) / Container Apps.
# See AZURE_MIGRATION.md for the full checklist - this image alone does not solve the
# local-disk/in-memory-state issues documented in CLAUDE.md sections 1 and 7; it just gives you
# a portable way to run the existing Flask app somewhere other than Render.

FROM python:3.11-slim

WORKDIR /app

# System deps for bokeh/numpy/scikit-learn wheels on slim images
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser \
    && mkdir -p /app/fantasy_analysis_output \
    && chown -R appuser:appuser /app
USER appuser

ENV PORT=8000
EXPOSE 8000

# Single worker, multiple threads: analysis_status/active_analyses in server.py are in-memory
# and process-local - see CLAUDE.md section 7 and server.py's __main__ comment. Do not raise
# --workers above 1 without first moving that state to an external store (Redis/Table Storage).
CMD ["sh", "-c", "gunicorn server:app --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:${PORT}"]
