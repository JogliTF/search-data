import json
import os
from datetime import datetime
from pathlib import Path

import mysql.connector
import yaml
from dotenv import load_dotenv

from app.intelligence.gemini_topic_selector import select_topic_with_gemini


def load_cfg():
    load_dotenv(override=True)
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def db_connect():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DB"),
    )


def get_latest_success_run_id(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM trend_run WHERE status='success' ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    cur.close()
    if not row:
        raise RuntimeError("No hay runs 'success' en trend_run. Ejecuta primero el paso YouTube.")
    return int(row[0])


def get_top_candidates(conn, run_id: int, limit: int = 20):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT topic, source, score, metrics_json
        FROM trend_candidate
        WHERE run_id=%s
        ORDER BY score DESC
        LIMIT %s;
        """,
        (run_id, limit),
    )
    rows = cur.fetchall()
    cur.close()

    # metrics_json puede venir como str o dict
    for r in rows:
        mj = r.get("metrics_json")
        if isinstance(mj, str) and mj:
            try:
                r["metrics"] = json.loads(mj)
            except Exception:
                r["metrics"] = {"raw": mj}
        elif isinstance(mj, (dict, list)):
            r["metrics"] = mj
        else:
            r["metrics"] = {}
    return rows


def upsert_selected_topic(conn, run_id: int, selection: dict):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO selected_topic
          (run_id, topic_title, topic_summary, platform_focus, keywords_json, angles_json, why_selected, evidence_json)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          topic_title=VALUES(topic_title),
          topic_summary=VALUES(topic_summary),
          platform_focus=VALUES(platform_focus),
          keywords_json=VALUES(keywords_json),
          angles_json=VALUES(angles_json),
          why_selected=VALUES(why_selected),
          evidence_json=VALUES(evidence_json);
        """,
        (
            run_id,
            selection["topic_title"],
            selection.get("topic_summary"),
            selection["platform_focus"],
            json.dumps(selection["keywords"], ensure_ascii=False),
            json.dumps(selection["angles"], ensure_ascii=False),
            selection["why_selected"],
            json.dumps(selection["evidence"], ensure_ascii=False),
        ),
    )
    conn.commit()
    cur.close()


def main():
    cfg = load_cfg()

    # Verificar API key de Gemini
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        raise RuntimeError("Falta GOOGLE_API_KEY o GEMINI_API_KEY en .env")

    region = os.getenv("REGION", "PE")
    language = os.getenv("LANGUAGE") or cfg["regions_supported"].get(region, {}).get("default_language", "es")
    allowed_niches = cfg["niches"]["allowed"]

    conn = db_connect()

    try:
        run_id = int(os.getenv("RUN_ID") or get_latest_success_run_id(conn))
        top_k = int(cfg["radar"]["top_k_candidates"])

        candidates = get_top_candidates(conn, run_id, limit=top_k)
        if not candidates:
            raise RuntimeError(f"No hay candidatos en trend_candidate para run_id={run_id}")

        # Usar Gemini en lugar de OpenAI
        selection = select_topic_with_gemini(
            region=region,
            language=language,
            allowed_niches=allowed_niches,
            candidates=candidates,
        )

        # Construimos topic_package completo (metadatos + selección + resumen de candidatos)
        topic_package = {
            "run_id": run_id,
            "region": region,
            "language": language,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "topic_title": selection["topic_title"],
            "topic_summary": selection["topic_summary"],
            "keywords": selection["keywords"],
            "niches_matched": selection["niches_matched"],
            "platform_focus": selection["platform_focus"],
            "angles": selection["angles"],
            "why_selected": selection["why_selected"],
            "evidence": selection["evidence"],
            "candidates_top": [
                {"topic": c["topic"], "source": c["source"], "score": float(c["score"])}
                for c in candidates
            ],
        }

        # Guardar en MySQL
        upsert_selected_topic(conn, run_id, selection)

        # Guardar JSON a disco
        out_dir = Path("data/runs")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"run_{run_id}_topic_package.json"
        out_path.write_text(json.dumps(topic_package, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[OK] run_id={run_id}")
        print(f"[OK] selected topic: {selection['topic_title']}")
        print(f"[OK] wrote: {out_path}")
        print(f"[OK] powered by: Gemini ({os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')})")

    finally:
        conn.close()


if __name__ == "__main__":
    main()