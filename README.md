# WebLINK Bridge Service

Python Flask service that receives sensor data from the [ESP32-S3 Gateway](https://github.com/mbudit/weblink-monitor) and stores it in PostgreSQL.

---

## Overview

The bridge sits between the ESP32-S3 firmware and a PostgreSQL database. It receives periodic JSON payloads over HTTP POST and persists them as JSONB records. Designed to run as a Docker container on a local LAN, with a lightweight local development workflow for Windows and Linux.

---

## Features

- **Flask HTTP API** — receives sensor JSON payloads
- **PostgreSQL connection pooling** via `psycopg2` (`ThreadedConnectionPool`)
- **Auto-initializes the database** — creates the database and `sensor_log` table on first run
- **Health endpoint** — `GET /health` for liveness probes (container orchestration)
- **Timezone-aware** — all timestamps stored as `TIMESTAMPTZ` in `Asia/Jakarta`
- **Windows & Linux venv** support for local development

---

## Environment Variables

| Variable   | Default              | Description                          |
|------------|----------------------|--------------------------------------|
| `DB_HOST`  | `192.168.101.215`    | PostgreSQL server hostname/IP        |
| `DB_PORT`  | `5432`               | PostgreSQL port                      |
| `DB_NAME`  | `weblink`            | Target database name                 |
| `DB_USER`  | `pguser`             | Database username                    |
| `DB_PASS`  | `pgpass`             | Database password                    |
| `MAX_CONN` | `5`                  | Max connections in the pool          |

---

## Local Development

### Windows 11

```powershell
# Navigate to the bridge directory
cd "C:\Users\Budi\Desktop\Arduino Projects\weblink-monitor\bridge"

# Create a virtual environment
python -m venv venv

# Activate the venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the service (set DB_HOST if your DB is elsewhere)
$env:DB_HOST = "192.168.101.215"
python bridge.py
```

### Linux / macOS

```bash
# Navigate to the bridge directory
cd /path/to/weblink-monitor/bridge

# Create a virtual environment
python3 -m venv venv

# Activate the venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service
DB_HOST=192.168.101.215 python bridge.py
```

The service starts on `http://0.0.0.0:5000`.

---

## Docker Deployment

### Build and run

```bash
docker-compose up -d
```

### Update environment variables

Edit `docker-compose.yml` and change the `environment` block, then restart:

```bash
docker-compose down && docker-compose up -d --build
```

### View logs

```bash
docker-compose logs -f bridge
```

### Stop

```bash
docker-compose down
```

---

## API Endpoints

### `POST /api/data`

Receives sensor data from the ESP32 gateway. The body should be a JSON object matching the gateway's payload format.

**Request**
```
POST /api/data
Content-Type: application/json

{
  "kws":  { "v": 220.0, "c": 2.145, "p": 472.0, ... },
  "wellpro": [12.45, 13.21, 0.00, ...],
  "env":  { "temp": 32.4, "humi": 68.7 },
  ...
}
```

**Response**
```
201 Created
{ "status": "success", "message": "Data saved" }
```

**Error responses**
- `400` — missing or non-JSON body
- `503` — database unavailable
- `500` — internal processing error

### `GET /health`

Liveness probe — checks database connectivity.

**Response**
```
200 OK
{ "status": "healthy" }

503 Service Unavailable
{ "status": "unhealthy", "error": "..." }
```

---

## Database Schema

```sql
CREATE TABLE sensor_log (
    id        SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ip_addr   INET,
    data      JSONB
);

CREATE INDEX idx_sensor_log_timestamp ON sensor_log (timestamp DESC);
```

- `timestamp` — UTC time the record was inserted (stored as `TIMESTAMPTZ`, set to `Asia/Jakarta` on connection)
- `ip_addr` — IP address of the sending gateway
- `data` — full JSON payload from the ESP32 gateway (stored as JSONB)

---

## Project Structure

```
bridge/
├── bridge.py          # Flask application
├── Dockerfile         # python:3.9-slim container image
├── docker-compose.yml # Service definition
├── requirements.txt   # Python dependencies
└── README.md          # This file
```
