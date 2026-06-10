from __future__ import annotations

import base64
import json

from fastapi import UploadFile
from openai import OpenAI

from app.models import ImportResult, RouteCreate


ROUTE_SCHEMA = {
    "name": "route_profile",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "can_extract_route",
            "failure_reason",
            "name",
            "distance_km",
            "elevation_gain_m",
            "start_altitude_m",
            "end_altitude_m",
            "avg_grade_percent",
            "max_grade_percent",
            "segments",
        ],
        "properties": {
            "can_extract_route": {"type": "boolean"},
            "failure_reason": {"type": "string"},
            "name": {"type": "string"},
            "distance_km": {"type": "number"},
            "elevation_gain_m": {"type": "number"},
            "start_altitude_m": {"type": "number"},
            "end_altitude_m": {"type": "number"},
            "avg_grade_percent": {"type": "number"},
            "max_grade_percent": {"type": "number"},
            "segments": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["start_km", "end_km", "grade_percent", "start_altitude_m", "end_altitude_m"],
                    "properties": {
                        "start_km": {"type": "number"},
                        "end_km": {"type": "number"},
                        "grade_percent": {"type": "number"},
                        "start_altitude_m": {"type": "number"},
                        "end_altitude_m": {"type": "number"},
                    },
                },
            },
        },
    },
    "strict": True,
}


async def import_route_from_image(file: UploadFile, api_key: str) -> ImportResult:
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("Configura primero la API key de OpenAI en Ajustes.")

    contents = await file.read()
    mime_type = file.content_type or "image/png"
    image_b64 = base64.b64encode(contents).decode("ascii")
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analiza si la imagen contiene un perfil de altimetría de ciclismo o puerto con datos suficientes "
                            "para crear una ruta. Solo marca can_extract_route=true si se ven datos reales de distancia y "
                            "altitud o pendientes/tramos suficientes para construir segmentos. Si la imagen no es un perfil "
                            "de altimetría, es decorativa, está vacía, no contiene un puerto, o no tiene datos legibles, marca "
                            "can_extract_route=false y explica brevemente el motivo en failure_reason. No inventes una ruta "
                            "a partir de una imagen no relacionada. Si can_extract_route=true, devuelve los datos métricos visibles; "
                            "solo infiere pequeños huecos cuando la imagen sí es claramente una altimetría."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{image_b64}",
                        "detail": "high",
                    },
                ],
            }
        ],
        text={"format": {"type": "json_schema", **ROUTE_SCHEMA}},
    )

    if not response.output_text:
        raise ValueError("OpenAI no devolvió datos de ruta.")
    raw = json.loads(response.output_text)
    if not raw.get("can_extract_route"):
        reason = raw.get("failure_reason") or "la imagen no contiene todos los datos necesarios."
        raise ValueError(f"No se ha podido generar una ruta basada en la imagen porque {reason}")
    raw.pop("can_extract_route", None)
    raw.pop("failure_reason", None)
    raw["original_image_path"] = file.filename or "profile.png"
    draft = RouteCreate(**raw)
    draft.segments.sort(key=lambda segment: segment.start_km)
    validate_extracted_route(draft)
    return ImportResult(draft=draft, image_path=raw["original_image_path"])


def validate_extracted_route(draft: RouteCreate) -> None:
    valid_segments = [segment for segment in draft.segments if segment.end_km > segment.start_km]
    has_meaningful_altitude = any(
        abs(segment.end_altitude_m - segment.start_altitude_m) > 0 for segment in valid_segments
    )
    if draft.distance_km <= 0 or not valid_segments or not has_meaningful_altitude:
        raise ValueError(
            "No se ha podido generar una ruta basada en la imagen porque no contiene todos los datos necesarios."
        )
