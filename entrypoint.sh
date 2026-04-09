#!/bin/bash
set -e

mkdir -p /app/backend/data

# Seed database on first run
if [ ! -f /app/backend/data/database.db ]; then
    echo "Seeding database..."
    cd /app/backend && DB_PATH=/app/backend/data/database.db python seed.py
fi

# Set up cron jobs
cat > /etc/cron.d/garcia << 'CRONEOF'
0 16 * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m reminders.run_reminders >> /var/log/garcia-reminders.log 2>&1
0 */2 * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m waitlist.run_waitlist >> /var/log/garcia-waitlist.log 2>&1
*/30 * * * * root cd /app/automation && DB_PATH=/app/backend/data/database.db python -m watchdog.run_watchdog >> /var/log/garcia-watchdog.log 2>&1
CRONEOF
chmod 0644 /etc/cron.d/garcia
cron

echo "Starting Garcia Folklorico API on port 8000..."
cd /app/backend
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000
