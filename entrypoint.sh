#!/bin/bash
set -e

mkdir -p /app/backend/data

# Decode Google credentials from base64 env var (if provided)
if [ -n "$GOOGLE_CREDS_B64" ]; then
    echo "$GOOGLE_CREDS_B64" | base64 -d > /app/automation/google_creds.json
    export GOOGLE_SHEETS_CREDS=/app/automation/google_creds.json
    echo "Google Sheets credentials decoded."
fi

# Seed database on first run
if [ ! -f /app/backend/data/database.db ]; then
    echo "Seeding database..."
    cd /app/backend && DB_PATH=/app/backend/data/database.db python seed.py
fi

# Run schema migrations (idempotent)
echo "Running schema migrations..."
cd /app/backend && DB_PATH=/app/backend/data/database.db python migrate.py

# Set up cron jobs
cat > /etc/cron.d/garcia << 'CRONEOF'
0 16 * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m reminders.run_reminders >> /var/log/garcia-reminders.log 2>&1
0 */2 * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m waitlist.run_waitlist >> /var/log/garcia-waitlist.log 2>&1
*/5 * * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m crm_events.run_crm_events >> /var/log/garcia-crm-events.log 2>&1
*/15 * * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m sheets_sync.run_sync >> /var/log/garcia-sheets-sync.log 2>&1
*/30 * * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m watchdog.run_watchdog >> /var/log/garcia-watchdog.log 2>&1
0 7 * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m digest.run_digest >> /var/log/garcia-digest.log 2>&1
0 1 * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m block_transition.run_transition >> /var/log/garcia-block-transition.log 2>&1
CRONEOF
chmod 0644 /etc/cron.d/garcia
cron

echo "Starting Garcia Folklorico API on port 8000..."
cd /app/backend
export EVENTS_DIR=/app/automation/pipeline_events
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000
