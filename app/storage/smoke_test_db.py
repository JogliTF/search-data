import os
from datetime import datetime
import yaml
from dotenv import load_dotenv
import mysql.connector


def load_config():
    # Carga .env
    load_dotenv()

    # Lee config.yaml (solo para validar que existe y parsea)
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    return cfg


def get_db_connection():
    print(os.getenv("MYSQL_HOST", "localhost"))
    print(os.getenv("MYSQL_DB"))
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB")

    if not user or not database:
        raise RuntimeError("Faltan MYSQL_USER o MYSQL_DB en el .env")

    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )


def main():
    cfg = load_config()

    region = os.getenv("REGION", "PE")
    language = os.getenv("LANGUAGE", cfg["regions_supported"].get(region, {}).get("default_language", "es"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) Crear run
    cursor.execute(
        """
        INSERT INTO trend_run (region, language, status, started_at)
        VALUES (%s, %s, 'running', NOW())
        """,
        (region, language),
    )
    run_id = cursor.lastrowid
    conn.commit()

    print(f"[OK] Created trend_run id={run_id} region={region} language={language}")

    # 2) Marcar éxito
    cursor.execute(
        """
        UPDATE trend_run
        SET status='success', finished_at=NOW()
        WHERE id=%s
        """,
        (run_id,),
    )
    conn.commit()

    print(f"[OK] Updated trend_run id={run_id} -> success")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
