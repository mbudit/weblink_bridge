import os
import sys
import json
import logging
import psycopg2
from psycopg2 import pool
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import Json
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("bridge")


# --- Configuration (from environment) ---
DB_HOST     = os.getenv("DB_HOST", "192.168.101.215")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "weblink")
DB_USER     = os.getenv("DB_USER", "pguser")
DB_PASS     = os.getenv("DB_PASS", "pgpass")
MAX_CONN    = int(os.getenv("MAX_CONN", "5"))   # Max pool connections

# --- Connection Pool ---
# ThreadedConnectionPool(minconn, maxconn, ...) — shared across requests.
# Connections are recycled; timezone is set once per connection in get_conn().
_db_pool = None

def get_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = pool.ThreadedConnectionPool(
            1, MAX_CONN,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            connect_timeout=5
        )
        logger.info(f"DB pool created: 1–{MAX_CONN} connections to {DB_HOST}:{DB_PORT}/{DB_NAME}")
    return _db_pool

def get_db_connection():
    """Get a connection from the pool. Caller must call conn.close() when done."""
    p = get_pool()
    conn = p.getconn()
    # Set timezone once per physical connection (persists for this session)
    with conn.cursor() as cur:
        cur.execute("SET timezone = 'Asia/Jakarta';")
    return conn

def release_conn(conn):
    """Return connection to the pool."""
    p = get_pool()
    p.putconn(conn)

def init_db():
    """Create the database and table if they don't exist."""
    logger.info("Initializing database...")

    # 1. Connect to 'postgres' default DB to create the target DB if needed
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, database="postgres",
            user=DB_USER, password=DB_PASS, connect_timeout=5
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        cur.execute(
            "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s",
            (DB_NAME,)
        )
        if not cur.fetchone():
            logger.info(f"Creating database '{DB_NAME}'...")
            cur.execute(f"CREATE DATABASE {DB_NAME}")
            logger.info(f"Database '{DB_NAME}' created.")
        else:
            logger.debug(f"Database '{DB_NAME}' already exists.")

        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Warning checking/creating database: {e}")
        # Continue anyway — DB may already exist but be reachable

    # 2. Create the sensor_log table in the target DB
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_log (
                id        SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                ip_addr   INET,
                data      JSONB
            );
        """)
        # Index on timestamp for efficient time-range queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sensor_log_timestamp
            ON sensor_log (timestamp DESC);
        """)
        conn.commit()
        cur.close()
        release_conn(conn)
        logger.info(f"Table 'sensor_log' ready in '{DB_NAME}'.")
    except Exception as e:
        logger.error(f"Error initializing table: {e}")
        raise  # Fatal — cannot proceed without the table

@app.route('/api/data', methods=['POST'])
def receive_data():
    # Validate Content-Type
    if not request.is_json:
        logger.warning(f"Rejected non-JSON request from {request.remote_addr}")
        return jsonify({"status": "error", "message": "Content-Type must be application/json"}), 400

    try:
        data = request.json
        sender_ip = request.remote_addr

        # Log incoming data summary
        device_id = data.get("sys", {}).get("id", "unknown")
        kws = data.get("kws", {})
        wellpro = data.get("wellpro", [])
        env = data.get("env", {})
        links = data.get("links", [])
        logger.info(
            f"INCOMING from {sender_ip} | device={device_id} | "
            f"kws_v={kws.get('v')} kws_c={kws.get('c')} | "
            f"wellpro_ch={len(wellpro)} | env_temp={env.get('temp')} | "
            f"links={len(links)}"
        )

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sensor_log (ip_addr, data) VALUES (%s, %s)",
            (sender_ip, Json(data))
        )
        conn.commit()
        cur.close()
        release_conn(conn)

        logger.info(f"Saved sensor data from {sender_ip} (device={device_id})")
        return jsonify({"status": "success", "message": "Data saved"}), 201

    except psycopg2.OperationalError as e:
        logger.error(f"DB connection error on request from {request.remote_addr}: {e}")
        return jsonify({"status": "error", "message": "Database unavailable"}), 503
    except Exception as e:
        logger.error(f"Error processing request from {request.remote_addr}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Liveness probe for container orchestration."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.close()
        release_conn(conn)
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

if __name__ == '__main__':
    logger.info("Bridge service starting up...")
    logger.info(f"Connecting to DB at {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}")
    init_db()
    logger.info("Bridge ready — listening on 0.0.0.0:5000")
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)