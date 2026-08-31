import json
import os
from typing import Any, Dict, List

from openai import OpenAI


def build_selection_schema() -> Dict[str, Any]:
    # Structured Outputs (JSON Schema) para asegurar JSON válido
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "topic_title": {"type": "string", "minLength": 10, "maxLength": 120},
            "topic_summary": {"type": "string", "minLength": 20, "maxLength": 280},
            "platform_focus": {"type": "string", "enum": ["youtube", "tiktok", "both"]},
            "keywords": {
                "type": "array",
                "minItems": 10,
                "maxItems": 20,
                "items": {"type": "string", "minLength": 3, "maxLength": 40},
            },
            "niches_matched": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "angles": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "angle_title": {"type": "string", "minLength": 6, "maxLength": 80},
                        "angle_hook": {"type": "string", "minLength": 10, "maxLength": 120},
                        "uniqueness_note": {"type": "string", "minLength": 10, "maxLength": 160},
                    },
                    "required": ["angle_title", "angle_hook", "uniqueness_note"],
                },
            },
            "why_selected": {"type": "string", "minLength": 40, "maxLength": 500},
            "evidence": {
                "type": "array",
                "minItems": 3,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "source": {"type": "string", "enum": ["youtube", "google_trends", "tiktok"]},
                        "signal": {"type": "string", "minLength": 10, "maxLength": 160},

                        # ✅ CAMBIO CLAVE:
                        # Con strict=True, NO conviene "object" porque las keys varían.
                        # Lo devolvemos como string con JSON serializado.
                        "metrics": {"type": "string", "maxLength": 1200},
                    },
                    "required": ["source", "signal", "metrics"],
                },
            },
        },
        "required": [
            "topic_title",
            "topic_summary",
            "platform_focus",
            "keywords",
            "niches_matched",
            "angles",
            "why_selected",
            "evidence",
        ],
    }


def select_topic_with_openai(
    *,
    region: str,
    language: str,
    allowed_niches: List[str],
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    candidates: lista de objetos con {topic, score, source, metrics_json}
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI()

    # Reducimos ruido: mandamos al LLM solo lo esencial
    compact_candidates = [
        {
            "topic": c["topic"],
            "score": float(c["score"]),
            "source": c.get("source", "youtube"),
            "metrics": c.get("metrics", {}),
        }
        for c in candidates
    ]

    system_msg = (
        "Eres un estratega de contenido viral faceless para videos de +60s. "
        "Tu objetivo es elegir un tema ganador para HOY y proponer 3 ángulos narrativos únicos "
        "que eviten copiar el enfoque común. Debes basarte en los candidatos y sus scores."
    )

    user_msg = {
        "region": region,
        "language": language,
        "allowed_niches": allowed_niches,
        "candidates_top": compact_candidates,
        "instructions": [
            "Elige un SOLO tema ganador y conviértelo en un topic_title narrativo (no una sola palabra).",
            "Genera 10-20 keywords útiles para guion y SEO.",
            "Devuelve 3 ángulos distintos con hook (0-5s) y nota de originalidad.",
            "Plataforma: si hoy aplica a ambas, usa 'both'; si no, 'youtube' por defecto.",
            "No uses claims médicos/legales; evita difamación; mantén tono para público general.",
            # ✅ Importante: metrics debe ser STRING (JSON serializado)
            "En evidence.metrics devuelve un STRING con JSON (ej: '{\"views\":123,\"velocity_24h\":0.25}'), no un objeto.",
            "Devuelve SOLO JSON según el schema.",
        ],
    }

    schema = build_selection_schema()

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": json.dumps(user_msg, ensure_ascii=False)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "topic_selection",
                "strict": True,
                "schema": schema,
            }
        },
    )

    selection = json.loads(response.output_text)

    # 🛡️ (Opcional) Por si el modelo devolviera metrics como dict/array por accidente,
    # lo normalizamos a string para cumplir el contrato.
    for ev in selection.get("evidence", []):
        m = ev.get("metrics")
        if isinstance(m, (dict, list)):
            ev["metrics"] = json.dumps(m, ensure_ascii=False)

    return selection