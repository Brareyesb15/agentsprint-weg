"""Núcleo del agente — carril de Brandon.

Piezas independientes del reto (escritas antes de conocerlo):
  events      los 8 eventos SSE de team/CONTRATOS.md
  sources     forma canónica de una fuente + normalización de números y unidades
  guardrails  el guard de citas determinista
  memory      depósito de hechos de sesión
  tools       registro de herramientas con la firma del contrato
  images      reescalado de imágenes antes de enviarlas al modelo
  keys        rotación de las 4 API keys con reintento
  llm         adaptador del SDK de Gemini (única capa que conoce la API)
  loop        el loop think -> act -> observe
"""
