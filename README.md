# Guestbook

A public guestbook at **https://guestbook.emilabraham.com** where visitors can leave messages that print on the Rongta RP326 thermal printer on Emil's desk.

---

## How It Works

```
Browser → guestbook.emilabraham.com (Apache) → this API (port 8766) → printer-server (port 8765) → /dev/usb/lp0
```

1. A visitor submits a message on the website.
2. Apache proxies the request to this API running on `127.0.0.1:8766`.
3. The API validates and sanitizes the message (see Security below).
4. If rate limits pass, the message is saved to `guestbook.db` and forwarded to the printer server on port 8765.
5. The printer server sends it to the thermal printer via ESC/POS commands.

---

## File Layout

```
/home/emil/guestbook/
├── app.py                  # FastAPI backend (the API itself)
├── guestbook.db            # SQLite database (auto-created on first run)
├── guestbook.service       # systemd service definition
├── guestbook-apache.conf   # Apache VirtualHost source config
├── static/
│   └── index.html          # Frontend source (edit this, then run deploy.sh)
├── deploy.sh               # Copies static/ to /var/www/guestbook/
├── venv/                   # Python virtual environment with dependencies
└── README.md               # This file

/etc/systemd/system/guestbook.service       # Installed copy of service file
/etc/apache2/sites-enabled/guestbook.conf           # Apache HTTP config (managed by certbot)
/etc/apache2/sites-enabled/guestbook-le-ssl.conf    # Apache HTTPS config (managed by certbot)
/var/www/guestbook/                                 # Deployed frontend (do not edit directly)
```

**Dependencies** (installed in `venv/`): `fastapi`, `uvicorn`, `slowapi`

**Related services:**
- `printer-server.service` — runs `~/printer-server.py` on port 8765. The guestbook API depends on this.

## Updating the Frontend

Edit `static/index.html`, then deploy:

```bash
sudo ./deploy.sh
```

---

## Service Management

```bash
# Status
sudo systemctl status guestbook

# Start / Stop / Restart
sudo systemctl start guestbook
sudo systemctl stop guestbook
sudo systemctl restart guestbook

# View logs (live)
sudo journalctl -u guestbook -f

# View recent logs
sudo journalctl -u guestbook -n 50
```

The service is enabled to start automatically on boot. To change that:

```bash
sudo systemctl disable guestbook   # stop auto-start
sudo systemctl enable guestbook    # re-enable auto-start
```

---

## Configuration

Configuration is set via environment variables in `guestbook.service`:

| Variable | Default | Description |
|---|---|---|
| `DAILY_LIMIT` | `30` | Max messages accepted globally per day |

To change a setting:

1. Edit `/etc/systemd/system/guestbook.service` (or `~/guestbook/guestbook.service` and re-copy it).
2. Run `sudo systemctl daemon-reload && sudo systemctl restart guestbook`.

---

## API Endpoints

### `POST /submit`
Accepts a message and prints it.

**Rate limits:**
- 3 requests per hour per IP
- 30 messages per day globally (across all IPs)

**Request:**
```json
{ "message": "Hello!" }
```

**Responses:**
- `200` — accepted and printed
- `400` — message empty or contains no printable content
- `422` — malformed request (e.g. missing `message` field)
- `429` — rate limit exceeded
- `502` — printer unavailable

**Test with Python:**
```python
import urllib.request, json
payload = json.dumps({'message': 'test'}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:8766/submit',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as r:
    print(r.read())
```

### `GET /gallery`
Returns messages that have been approved for gallery display (none by default).

---

## Security

### Input Sanitization
All messages are sanitized before printing:
- Characters `0x00–0x1F` are stripped — this includes **ESC (`0x1B`)** and **GS (`0x1D`)**, which are the command prefixes for ESC/POS printer control. Without this, a visitor could send raw printer commands.
- `0x7F` (DEL) and Unicode control/format categories are also stripped.
- Newlines (`0x0A`) are preserved.
- All other printable Unicode is allowed.

Sanitization happens in the API **before** the message reaches the printer server.

### Character Limit
Messages are capped at 10,000 characters.

---

## Debugging

**Service won't start:**
```bash
sudo journalctl -u guestbook -n 30
# Look for Python tracebacks or port conflicts
```

**Printer not printing but API returns 200:**
```bash
# Check the printer server is running
sudo systemctl status printer-server

# Check the printer device exists
ls /dev/usb/lp0

# Test the printer server directly
python3 -c "
import urllib.request, json
payload = json.dumps({'message': 'test'}).encode()
req = urllib.request.Request('http://127.0.0.1:8765/print', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req) as r:
    print(r.read())
"
```

**Rate limit hit during testing:**

The rate limit is per-IP and resets after 1 hour. To reset it immediately, restart the service (rate limit state is in-memory):
```bash
sudo systemctl restart guestbook
```

**Check what's in the database:**
```bash
# sqlite3 is not installed — use Python instead:
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/emil/guestbook/guestbook.db')
rows = conn.execute('SELECT id, submitted_at, message FROM messages ORDER BY id DESC LIMIT 10').fetchall()
for r in rows:
    print(f'[{r[0]}] {r[1]}\n{r[2]}\n')
"
```

**Port already in use:**
```bash
sudo ss -tlnp | grep 8766
# Kill whatever is using it, then restart the service
```
