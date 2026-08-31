import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Any

import requests


STOPWORDS_ES = {
    "el","la","los","las","un","una","unos","unas","de","del","al","a","y","o","u",
    "en","por","para","con","sin","que","como","cuando","donde","quien","quienes",
    "esto","esta","este","estas","estos","es","son","fue","ser","se","su","sus",
    "lo","le","les","mi","mis","tu","tus","ya","más","mas","muy","pero","si","sí",
    "porque","qué","cuál","cuales","cómo","cuándo","dónde","quién"
}

def _clean_words(text: str) -> List[str]:
    # baja a minúsculas, deja letras/números/espacios
    t = text.lower()
    t = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", t)
    parts = [p.strip() for p in t.split() if p.strip()]
    # filtra stopwords y tokens muy cortos
    return [p for p in parts if len(p) >= 3 and p not in STOPWORDS_ES]


def fetch_youtube_popular_videos(region: str, api_key: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    MVP: usa videos.list chart=mostPopular.
    Devuelve lista de items (id + snippet + statistics).
    """
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": max_results,
        "key": api_key,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("items", [])


def videos_to_candidates(items: List[Dict[str, Any]], top_k: int = 20) -> List[Dict[str, Any]]:
    """
    Convierte videos a "candidatos" por keywords:
    - Cuenta frecuencia de palabras relevantes en títulos
    - Usa views como señal secundaria
    """
    word_stats: Dict[str, Dict[str, float]] = {}
    now = datetime.now(timezone.utc).isoformat()

    for it in items:
        snippet = it.get("snippet", {})
        stats = it.get("statistics", {})
        title = snippet.get("title", "") or ""
        published_at = snippet.get("publishedAt", None)

        # views puede no existir en algunos casos
        views = float(stats.get("viewCount", 0) or 0)

        words = _clean_words(title)
        for w in words:
            if w not in word_stats:
                word_stats[w] = {"count": 0.0, "views_sum": 0.0}
            word_stats[w]["count"] += 1.0
            word_stats[w]["views_sum"] += views

    # Score simple MVP: frecuencia normalizada + (views_sum normalizado)
    # (esto lo refinamos luego con momentum real, saturación, etc.)
    if not word_stats:
        return []

    max_count = max(v["count"] for v in word_stats.values()) or 1.0
    max_views = max(v["views_sum"] for v in word_stats.values()) or 1.0

    candidates = []
    for word, v in word_stats.items():
        count_norm = v["count"] / max_count
        views_norm = v["views_sum"] / max_views
        score = 0.7 * count_norm + 0.3 * views_norm

        candidates.append({
            "topic": word,
            "source": "youtube",
            "score": round(float(score), 6),
            "metrics": {
                "count_in_titles": int(v["count"]),
                "views_sum": int(v["views_sum"]),
                "generated_at": now,
            }
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]
