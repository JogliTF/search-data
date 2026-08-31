topic_package.json (salida del PASO 1)

Campos obligatorios:
- run_id: ID del run en BD
- region: PE/MX/ES/US_HISPANO
- language: es
- generated_at: timestamp ISO
- topic_title: string
- topic_summary: 1-2 líneas (qué trata)
- keywords: lista 10-20
- niches_matched: lista de nichos detectados (de config.yaml)
- platform_focus: youtube | tiktok | both

- angles: lista de 3 objetos:
   - angle_title: título corto del enfoque
   - angle_hook: gancho en 1 línea (0-5s)
   - uniqueness_note: por qué no es copia (en qué se diferencia)

- evidence: lista de señales (mínimo 3):
   - source: youtube/google_trends/tiktok
   - signal: texto corto (ej. "video con alta tracción 24h")
   - metrics: json (views, velocity, interest, etc.)

- candidates_top: lista (resumen) top 20:
   - topic
   - source
   - score
