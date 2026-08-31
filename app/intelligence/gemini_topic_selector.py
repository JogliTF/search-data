import json
import os
from typing import Any, Dict, List

from google import genai


def build_selection_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "topic_title": {"type": "string", "minLength": 10, "maxLength": 120},
            "topic_summary": {"type": "string", "minLength": 20, "maxLength": 280},
            "platform_focus": {"type": "string", "enum": ["youtube", "tiktok", "both"]},
            "selected_candidates": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 3, "maxLength": 80},
            },
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
                        # 🔑 metrics flexible => string JSON
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
            "selected_candidates",
        ],
    }


def select_topic_with_gemini(
    *,
    region: str,
    language: str,
    allowed_niches: List[str],
    candidates: List[Dict[str, Any]],
    
) -> Dict[str, Any]:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GOOGLE_API_KEY o GEMINI_API_KEY en .env")

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    print("CWD:", os.getcwd())
    print("ENV GEMINI_MODEL:", os.getenv("GEMINI_MODEL"))
    print("MODEL FINAL:", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    compact_candidates = [
        {
            "topic": c["topic"],
            "score": float(c["score"]),
            "source": c.get("source", "youtube"),
            "metrics": c.get("metrics", {}),
        }
        for c in candidates
    ]

    system_instruction = (
      "Eres un estratega de contenido viral faceless para videos de 60-75s. "
      "Tu misión: elegir un tema ganador PARA HOY basándote SOLO en candidates_top "
      "y proponer 3 ángulos con tono de historias reales tipo Reddit: confesiones, dilemas, "
      "casos extraños reales, conflictos humanos, giros, preguntas abiertas. "
      "Evita temas abstractos o genéricos si no están claramente representados en candidates_top. "
      "No difames ni identifiques personas reales; evita claims médicos/legales.\n\n"
      "Responde ÚNICAMENTE con JSON válido, sin texto extra."
    )

    schema = build_selection_schema()

    user_payload = {
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
            "En evidence.metrics devuelve un STRING con JSON serializado (ej: '{\"views\":123,\"velocity_24h\":0.25}'), no un objeto.",
            "Devuelve SOLO JSON y cumple el schema.",
            "El tema DEBE derivarse de 1 a 3 'topic' EXACTOS de candidates_top. No inventes temas fuera de esa lista.",
            "Devuelve selected_candidates con 1-3 strings que coincidan EXACTAMENTE con candidates_top[].topic.",
            "Los ángulos deben sonar a historia real: plantea un caso, una escena o un dilema humano y un giro.",
            "El hook debe ser tipo Reddit: 'Esto pasó y nadie lo vio venir...' o '¿Soy el malo por...?' (sin copiar literal).",
        ],
        "output_schema": schema,
    }

    client = genai.Client(api_key=api_key)

    # Forzamos salida JSON
    response = client.models.generate_content(
        model=model_name,
        contents=[
            system_instruction,
            json.dumps(user_payload, ensure_ascii=False),
        ],
        config={
            "temperature": 0.2,
            "max_output_tokens": 4096,
            "response_mime_type": "application/json",
        },
    )

    text = (response.text or "").strip()

    # Parseo robusto (por si viene con fences)
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        text = text.replace("json", "", 1).strip()


    print("RAW RESPONSE START >>>")
    print(text[:1500])
    print("<<< RAW RESPONSE END")

    selection = json.loads(text)

    # Validaciones mínimas (igual que tu código)
    required_fields = [
        "topic_title", "topic_summary", "platform_focus",
        "keywords", "niches_matched", "angles",
        "why_selected", "evidence"
    ]

    candidate_topics = {c["topic"] for c in compact_candidates}
    for t in selection.get("selected_candidates", []):
        if t not in candidate_topics:
            raise ValueError(f"selected_candidates contiene '{t}' que NO está en candidates_top")

    for field in required_fields:
        if field not in selection:
            raise ValueError(f"Campo requerido '{field}' no encontrado en la respuesta")

    if len(selection["keywords"]) < 10:
        raise ValueError(f"Se requieren al menos 10 keywords, recibido: {len(selection['keywords'])}")
    if len(selection["angles"]) != 3:
        raise ValueError(f"Se requieren exactamente 3 ángulos, recibido: {len(selection['angles'])}")
    if len(selection["evidence"]) < 3:
        raise ValueError(f"Se requieren al menos 3 evidencias, recibido: {len(selection['evidence'])}")

    # Normaliza metrics (por si el modelo igual manda dict/list)
    for ev in selection.get("evidence", []):
        m = ev.get("metrics")
        if isinstance(m, (dict, list)):
            ev["metrics"] = json.dumps(m, ensure_ascii=False)

    return selection