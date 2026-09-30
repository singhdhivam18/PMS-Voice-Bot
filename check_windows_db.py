import psycopg

conn = psycopg.connect(
    host="127.0.0.1",
    port=5432,
    dbname="dev-voice-db",
    user="postgres",
    password="Test@123",
)

with conn.cursor() as cur:
    cur.execute("""
        SELECT
            inet_server_addr(),
            inet_server_port(),
            current_database(),
            current_user,
            version()
    """)
    print("SERVER:", cur.fetchone())

    cur.execute("SELECT COUNT(*) FROM public.vehicle_service")
    print("vehicle_service count:", cur.fetchone()[0])

    cur.execute("""
        SELECT id, vehicle_id, service_status, due_maintenance_date
        FROM public.vehicle_service
        ORDER BY id
    """)
    print("vehicle_service rows:", cur.fetchall())

conn.close()
