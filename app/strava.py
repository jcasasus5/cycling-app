from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import httpx

from app.models import ActivityDetail


STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_UPLOAD_URL = "https://www.strava.com/api/v3/uploads"
STRAVA_REVOKE_URL = "https://www.strava.com/oauth/revoke"
OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60
TCX_NAMESPACE = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
ACTIVITY_EXTENSION_NAMESPACE = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"


class StravaError(RuntimeError):
    pass


@dataclass(frozen=True)
class StravaTokens:
    access_token: str
    refresh_token: str
    expires_at: int


@dataclass(frozen=True)
class StravaUploadResult:
    upload_id: str
    activity_id: str
    status: str
    error: str = ""


def configured() -> bool:
    return all(
        os.getenv(name)
        for name in (
            "STRAVA_CLIENT_ID",
            "STRAVA_CLIENT_SECRET",
            "STRAVA_REDIRECT_URI",
            "APP_ENCRYPTION_KEY",
        )
    )


def require_configuration() -> None:
    missing = [
        name
        for name in (
            "STRAVA_CLIENT_ID",
            "STRAVA_CLIENT_SECRET",
            "STRAVA_REDIRECT_URI",
            "APP_ENCRYPTION_KEY",
        )
        if not os.getenv(name)
    ]
    if missing:
        raise StravaError(f"Falta configurar: {', '.join(missing)}.")


def create_oauth_state(
    user_id: str,
    *,
    now: int | None = None,
    nonce: str | None = None,
) -> str:
    require_configuration()
    payload = {
        "user_id": user_id,
        "issued_at": now if now is not None else int(time.time()),
        "nonce": nonce or secrets.token_urlsafe(18),
    }
    encoded_payload = _urlsafe_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_state_secret(), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_urlsafe_encode(signature)}"


def verify_oauth_state(state: str, user_id: str, *, now: int | None = None) -> None:
    try:
        encoded_payload, encoded_signature = state.split(".", 1)
        supplied_signature = _urlsafe_decode(encoded_signature)
        expected_signature = hmac.new(
            _state_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError
        payload = json.loads(_urlsafe_decode(encoded_payload))
        issued_at = int(payload["issued_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StravaError("El estado OAuth de Strava no es válido.") from exc

    current_time = now if now is not None else int(time.time())
    if payload.get("user_id") != user_id:
        raise StravaError("La autorización de Strava pertenece a otro usuario.")
    if issued_at > current_time + 60 or current_time - issued_at > OAUTH_STATE_MAX_AGE_SECONDS:
        raise StravaError("La autorización de Strava ha caducado. Vuelve a iniciarla.")


def authorization_url(user_id: str) -> tuple[str, str]:
    state = create_oauth_state(user_id)
    query = urlencode(
        {
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "redirect_uri": os.environ["STRAVA_REDIRECT_URI"],
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": "activity:write",
            "state": state,
        }
    )
    return f"{STRAVA_AUTHORIZE_URL}?{query}", state


def exchange_authorization_code(code: str) -> tuple[StravaTokens, dict[str, Any]]:
    require_configuration()
    try:
        response = httpx.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": os.environ["STRAVA_CLIENT_ID"],
                "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": os.environ["STRAVA_REDIRECT_URI"],
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise StravaError("No se ha podido contactar con Strava.") from exc
    payload = _response_payload(response, "No se ha podido conectar con Strava.")
    scopes = str(payload.get("scope") or "").replace(",", " ").split()
    if "activity:write" not in scopes:
        raise StravaError("Strava no ha concedido permiso para publicar actividades.")
    return _tokens_from_payload(payload), payload.get("athlete") or {}


def refresh_tokens(refresh_token: str) -> StravaTokens:
    require_configuration()
    try:
        response = httpx.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": os.environ["STRAVA_CLIENT_ID"],
                "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise StravaError("No se ha podido contactar con Strava.") from exc
    return _tokens_from_payload(_response_payload(response, "No se ha podido renovar la conexión con Strava."))


def revoke_token(token: str) -> None:
    require_configuration()
    credentials = f"{os.environ['STRAVA_CLIENT_ID']}:{os.environ['STRAVA_CLIENT_SECRET']}"
    authorization = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    try:
        response = httpx.post(
            STRAVA_REVOKE_URL,
            headers={"Authorization": f"Basic {authorization}"},
            data={"token": token, "token_type_hint": "refresh_token"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise StravaError("No se ha podido contactar con Strava.") from exc
    _response_payload(response, "No se ha podido desconectar Strava.", allow_empty=True)


def upload_activity(
    access_token: str,
    detail: ActivityDetail,
    external_id: str,
    *,
    poll_attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> StravaUploadResult:
    tcx = build_tcx(detail)
    try:
        response = httpx.post(
            STRAVA_UPLOAD_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={
                "name": detail.activity.route_name,
                "description": "Actividad de bici estática registrada con Climber.",
                "trainer": "1",
                "commute": "0",
                "data_type": "tcx",
                "sport_type": "VirtualRide",
                "external_id": external_id,
            },
            files={"file": (f"{external_id}.tcx", tcx, "application/vnd.garmin.tcx+xml")},
            timeout=60,
        )
    except httpx.HTTPError as exc:
        raise StravaError("No se ha podido contactar con Strava.") from exc
    payload = _response_payload(response, "Strava ha rechazado la actividad.")
    upload_id = str(payload.get("id_str") or payload.get("id") or "")
    if not upload_id:
        raise StravaError("Strava no ha devuelto el identificador de la subida.")

    result = _upload_result(upload_id, payload)
    if result.status != "pending":
        return result

    for _ in range(max(0, poll_attempts)):
        sleeper(1)
        try:
            result = get_upload_status(access_token, upload_id)
        except (StravaError, httpx.HTTPError):
            return result
        if result.status != "pending":
            return result
    return result


def get_upload_status(access_token: str, upload_id: str) -> StravaUploadResult:
    try:
        status_response = httpx.get(
            f"{STRAVA_UPLOAD_URL}/{upload_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise StravaError("No se ha podido contactar con Strava.") from exc
    status_payload = _response_payload(status_response, "No se ha podido consultar la subida en Strava.")
    return _upload_result(upload_id, status_payload)


def build_tcx(detail: ActivityDetail) -> bytes:
    ET.register_namespace("", TCX_NAMESPACE)
    ET.register_namespace("ae", ACTIVITY_EXTENSION_NAMESPACE)

    activity = detail.activity
    start_time = _parse_datetime(activity.started_at)
    root = ET.Element(_tag(TCX_NAMESPACE, "TrainingCenterDatabase"))
    activities = ET.SubElement(root, _tag(TCX_NAMESPACE, "Activities"))
    activity_element = ET.SubElement(activities, _tag(TCX_NAMESPACE, "Activity"), Sport="Biking")
    ET.SubElement(activity_element, _tag(TCX_NAMESPACE, "Id")).text = _format_datetime(start_time)
    lap = ET.SubElement(
        activity_element,
        _tag(TCX_NAMESPACE, "Lap"),
        StartTime=_format_datetime(start_time),
    )
    _text_element(lap, TCX_NAMESPACE, "TotalTimeSeconds", activity.active_seconds)
    _text_element(lap, TCX_NAMESPACE, "DistanceMeters", round(activity.distance_km * 1000, 2))
    max_speed_kph = max((sample.speed_kph for sample in detail.samples), default=activity.avg_speed_kph)
    _text_element(lap, TCX_NAMESPACE, "MaximumSpeed", round(max_speed_kph / 3.6, 3))
    _text_element(lap, TCX_NAMESPACE, "Calories", 0)
    _text_element(lap, TCX_NAMESPACE, "Intensity", "Active")
    _text_element(lap, TCX_NAMESPACE, "TriggerMethod", "Manual")
    track = ET.SubElement(lap, _tag(TCX_NAMESPACE, "Track"))

    for sample in detail.samples:
        point = ET.SubElement(track, _tag(TCX_NAMESPACE, "Trackpoint"))
        sample_time = start_time + timedelta(seconds=sample.elapsed_seconds)
        _text_element(point, TCX_NAMESPACE, "Time", _format_datetime(sample_time))
        _text_element(point, TCX_NAMESPACE, "AltitudeMeters", round(sample.altitude_m, 2))
        _text_element(point, TCX_NAMESPACE, "DistanceMeters", round(sample.km * 1000, 2))
        _text_element(point, TCX_NAMESPACE, "Cadence", max(0, sample.cadence_rpm))
        _text_element(point, TCX_NAMESPACE, "SensorState", "Present")
        extensions = ET.SubElement(point, _tag(TCX_NAMESPACE, "Extensions"))
        tpx = ET.SubElement(extensions, _tag(ACTIVITY_EXTENSION_NAMESPACE, "TPX"))
        _text_element(tpx, ACTIVITY_EXTENSION_NAMESPACE, "Speed", round(max(0, sample.speed_kph) / 3.6, 3))
        _text_element(tpx, ACTIVITY_EXTENSION_NAMESPACE, "Watts", max(0, sample.power_w))

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def athlete_name(athlete: dict[str, Any]) -> str:
    name = " ".join(part.strip() for part in (str(athlete.get("firstname") or ""), str(athlete.get("lastname") or "")) if part.strip())
    return name or str(athlete.get("username") or "Deportista de Strava")


def _upload_result(upload_id: str, payload: dict[str, Any]) -> StravaUploadResult:
    error = payload.get("error")
    if error:
        return StravaUploadResult(upload_id=upload_id, activity_id="", status="error", error=str(error))
    activity_id = str(payload.get("activity_id") or "")
    return StravaUploadResult(
        upload_id=upload_id,
        activity_id=activity_id,
        status="ready" if activity_id else "pending",
    )


def _tokens_from_payload(payload: dict[str, Any]) -> StravaTokens:
    try:
        return StravaTokens(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            expires_at=int(payload["expires_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StravaError("Strava ha devuelto credenciales incompletas.") from exc


def _response_payload(response: httpx.Response, fallback: str, *, allow_empty: bool = False) -> dict[str, Any]:
    if allow_empty and response.status_code < 400 and not response.content:
        return {}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        message = payload.get("message") or payload.get("error") or fallback
        raise StravaError(str(message))
    if not isinstance(payload, dict):
        raise StravaError(fallback)
    return payload


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _text_element(parent: ET.Element, namespace: str, name: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, _tag(namespace, name))
    element.text = str(value)
    return element


def _state_secret() -> bytes:
    secret = os.getenv("APP_ENCRYPTION_KEY")
    if not secret:
        raise StravaError("APP_ENCRYPTION_KEY no está configurada.")
    return secret.encode("utf-8")


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
