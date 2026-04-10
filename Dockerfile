FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends cron curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt gspread gspread-formatting stripe

COPY backend/ /app/backend/
COPY automation/ /app/automation/

RUN mkdir -p /app/backend/data /app/automation/pipeline_events /app/automation/watchdog

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
