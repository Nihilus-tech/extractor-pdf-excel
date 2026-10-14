# -*- coding: utf-8 -*-
"""
Provider-agnostic module for calling LLM providers (Groq, Gemini).
Knows nothing about invoices, PDFs, or business logic — only how to
send a prompt and get text back, with retries and fallback between
providers. Domain-specific code (ai_extractor.py) imports from here.
"""
import os
import time
from groq import Groq
from google import genai


class _RespuestaSimulada:
    """
    Wraps a Gemini response so it exposes the same shape as a Groq
    chat completion response — both response.choices[0].message.content
    and response.usage.prompt_tokens / completion_tokens. This lets
    callers parse the result and log usage metrics the same way
    regardless of which provider actually answered, with no branching
    needed downstream.
    """
    class _Choice:
        class _Message:
            def __init__(self, content):
                self.content = content

        def __init__(self, content):
            self.message = self._Message(content)

    class _Usage:
        def __init__(self, prompt_tokens, completion_tokens):
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens
            self.total_tokens = prompt_tokens + completion_tokens

    def __init__(self, texto, prompt_tokens=0, completion_tokens=0):
        self.choices = [self._Choice(texto)]
        self.usage = self._Usage(prompt_tokens, completion_tokens)


def _llamar_gemini_fallback(prompt: str):
    """
    Calls Gemini as a fallback provider when Groq is unavailable after
    all retries. Wraps the response in _RespuestaSimulada so callers
    can treat it identically to a Groq response, including token
    usage metrics.

    Args:
        prompt: the full prompt text to send to the model.

    Returns:
        A _RespuestaSimulada exposing .choices[0].message.content and
        .usage.prompt_tokens / .completion_tokens, matching the Groq
        response shape.

    Raises:
        Exception: whatever error Gemini raises, if the call fails.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt
    )

    # Gemini exposes token usage under a different attribute name and
    # structure than Groq. Extract defensively in case usage_metadata
    # is missing for some reason (e.g. a future SDK change).
    prompt_tokens = 0
    completion_tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
        completion_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

    return _RespuestaSimulada(response.text, prompt_tokens, completion_tokens)


def _llamar_groq_con_reintentos(client: Groq, prompt: str, max_intentos: int = 3, proveedor_forzado: str = None):
    """
    Dispatches a prompt to an LLM provider, with retries and automatic
    fallback. By default, tries Groq first (with exponential backoff
    retries) and falls back to Gemini if Groq cannot fulfill the
    request. If proveedor_forzado is set, skips straight to that
    provider instead — used when a user explicitly picks a provider
    for a single extraction or as their saved preference.

    Args:
        client: an initialized Groq client.
        prompt: the full prompt text to send to the model.
        max_intentos: maximum number of attempts before giving up on Groq.
        proveedor_forzado: if "gemini", skips Groq entirely and calls
            Gemini directly. If "groq" or None, uses the default
            Groq-first behavior with Gemini as fallback.

    Returns:
        A tuple (response, proveedor_usado, modelo_usado, latencia_ms):
        - response: the Groq API response object on success, or a
          _RespuestaSimulada from Gemini.
        - proveedor_usado: "groq" or "gemini", whichever actually
          answered — may differ from proveedor_forzado if a fallback
          occurred.
        - modelo_usado: the exact model name string that answered,
          for cost/audit tracking if the underlying model changes.
        - latencia_ms: wall-clock time spent on the successful call,
          in milliseconds, for observability metrics.

    Raises:
        Exception: the last error encountered, if the request cannot
            be fulfilled by any available provider.
    """
    MODELO_GROQ = "openai/gpt-oss-20b"
    MODELO_GEMINI = "gemini-flash-latest"

    # A user explicitly asked for Gemini — skip Groq's retries
    # entirely rather than making them wait for 3 failed Groq
    # attempts before getting the provider they actually wanted.
    if proveedor_forzado == "gemini":
        print("[ai_provider] Proveedor forzado a Gemini, se omite Groq.")
        inicio = time.time()
        respuesta = _llamar_gemini_fallback(prompt)
        latencia_ms = round((time.time() - inicio) * 1000)
        return respuesta, "gemini", MODELO_GEMINI, latencia_ms

    ultimo_error = None

    for intento in range(1, max_intentos + 1):
        try:
            inicio = time.time()
            respuesta = client.chat.completions.create(
                model=MODELO_GROQ,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1
            )
            latencia_ms = round((time.time() - inicio) * 1000)
            return respuesta, "groq", MODELO_GROQ, latencia_ms
            
            return respuesta, "groq", time.time() - inicio
        except Exception as e:
            ultimo_error = e
            mensaje_error = str(e)

            # Only retry on transient errors: rate limits, timeouts,
            # and 5xx server errors. Anything else (e.g. bad request,
            # auth failure) will not be fixed by waiting, so fail fast.
            es_reintentable = (
                "429" in mensaje_error
                or "rate_limit" in mensaje_error.lower()
                or "timeout" in mensaje_error.lower()
                or "500" in mensaje_error
                or "502" in mensaje_error
                or "503" in mensaje_error
                or isinstance(e, (ConnectionError, TimeoutError))
            )

            # If this specific error isn't worth retrying against Groq
            # again (e.g. bad request, auth failure), stop retrying but
            # still fall through to the Gemini fallback below — Groq
            # itself may be unable to help, but a different provider
            # might still succeed.
            if not es_reintentable:
                break

            if intento == max_intentos:
                break

            espera_segundos = 2 ** (intento - 1)  # 1s, 2s, 4s
            print(f"[ai_provider] Intento {intento}/{max_intentos} fallo: {mensaje_error}. Reintentando en {espera_segundos}s...")
            time.sleep(espera_segundos)

    # Groq could not fulfill the request, either because retries were
    # exhausted or because the error type wasn't worth retrying. Before
    # giving up entirely, attempt a single call to Gemini as a fallback
    # provider — this covers both transient Groq outages and cases
    # like an invalid/expired API key.
    print(f"[ai_provider] Groq fallo ({ultimo_error}). Intentando fallback con Gemini...")
    try:
        inicio = time.time()
        respuesta = _llamar_gemini_fallback(prompt)
        latencia_ms = round((time.time() - inicio) * 1000)
        return respuesta, "gemini", MODELO_GEMINI, latencia_ms
    except Exception as error_gemini:
        print(f"[ai_provider] Fallback con Gemini tambien fallo: {error_gemini}")
        raise ultimo_error



# Precios en USD por millon de tokens, confirmados contra la pagina
# oficial de precios de cada proveedor. Revisar y actualizar
# periodicamente — los proveedores cambian precios y modelos con
# frecuencia (ver el caso de llama-3.1-8b-instant deprecado en Groq).
PRECIOS_POR_MILLON_TOKENS = {
    "openai/gpt-oss-20b": {"entrada": 0.075, "salida": 0.30},
}


def calcular_costo_estimado_usd(modelo: str, tokens_entrada: int, tokens_salida: int) -> float:
    """
    Estimates the USD cost of a single LLM call based on a fixed,
    manually-maintained pricing table. Returns 0.0 for models not in
    the table (e.g. Gemini while on the free tier — see
    GEMINI_TIER_GRATUITO in .env) or if pricing is unknown.

    Args:
        modelo: the exact model name used for the call.
        tokens_entrada: input token count.
        tokens_salida: output token count.

    Returns:
        Estimated cost in USD, rounded to 6 decimal places.
    """
    if os.getenv("GEMINI_TIER_GRATUITO", "true").lower() == "true" and modelo == "gemini-flash-latest":
        return 0.0

    precios = PRECIOS_POR_MILLON_TOKENS.get(modelo)
    if not precios:
        return 0.0

    costo = (
        (tokens_entrada / 1_000_000) * precios["entrada"]
        + (tokens_salida / 1_000_000) * precios["salida"]
    )
    return round(costo, 6)
