from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from trading_oms_backend.event_journal import JsonlEventJournal

ALERT_INTENT_CREATED_EVENT_TYPE = "alert.intent.created"
ALERT_DISPATCH_RECORDED_EVENT_TYPE = "alert.dispatch.recorded"

VALID_ALERT_CHANNELS = {"local", "telegram"}
VALID_ALERT_SEVERITIES = {"informational", "warning", "critical", "emergency"}
VALID_DISPATCH_STATUSES = {"recorded", "failed"}

AlertChannel = Literal["local", "telegram"]
AlertSeverity = Literal["informational", "warning", "critical", "emergency"]
DispatchStatus = Literal["recorded", "failed"]

_SECRET_KEY_FRAGMENTS = {
    "account",
    "account_id",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bot_token",
    "certificate",
    "chat_id",
    "credential",
    "github_token",
    "openai_key",
    "password",
    "private_key",
    "secret",
    "token",
}

_SECRET_TEXT_MARKERS = (
    "api_key=",
    "api_key:",
    "authorization=",
    "authorization:",
    "bot_token=",
    "bot_token:",
    "chat_id=",
    "chat_id:",
    "password=",
    "password:",
    "private_key=",
    "private_key:",
    "secret=",
    "secret:",
    "token=",
    "token:",
)


class AlertError(ValueError):
    """Raised when alert inputs, payloads, or dispatch records are invalid."""


class AlertDispatcher(Protocol):
    def dispatch(
        self,
        alert: AlertIntent,
        request: AlertDispatchRequest,
    ) -> AlertDispatchOutcome:
        """Return a local dispatch outcome without requiring network delivery."""


@dataclass(frozen=True)
class AlertIntentRequest:
    alert_id: str
    source_event_type: str
    source_event_reference: str
    severity: str
    channel: str
    created_at: str
    title: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise AlertError("schema_version must be 1")
        _validated_identifier(self.alert_id, "alert_id")
        _validated_identifier(self.source_event_type, "source_event_type")
        _validated_identifier(self.source_event_reference, "source_event_reference")
        _validated_severity(self.severity)
        _validated_channel(self.channel)
        _parse_timestamp(self.created_at, "created_at")
        _validated_text(self.title, "title")
        _validated_text(self.message, "message")
        _validated_metadata(self.metadata)
        _assert_json_serializable(self.to_json_dict(), "alert intent request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "source_event_type": self.source_event_type,
            "source_event_reference": self.source_event_reference,
            "severity": self.severity,
            "channel": self.channel,
            "created_at": self.created_at,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AlertIntent:
    alert_id: str
    source_event_type: str
    source_event_reference: str
    severity: str
    channel: str
    created_at: str
    title: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_request(cls, request: AlertIntentRequest) -> AlertIntent:
        if not isinstance(request, AlertIntentRequest):
            raise AlertError("request must be an AlertIntentRequest")
        return cls(
            alert_id=request.alert_id,
            source_event_type=request.source_event_type,
            source_event_reference=request.source_event_reference,
            severity=request.severity,
            channel=request.channel,
            created_at=request.created_at,
            title=request.title,
            message=request.message,
            metadata=dict(request.metadata),
        )

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise AlertError("schema_version must be 1")
        _validated_identifier(self.alert_id, "alert_id")
        _validated_identifier(self.source_event_type, "source_event_type")
        _validated_identifier(self.source_event_reference, "source_event_reference")
        _validated_severity(self.severity)
        _validated_channel(self.channel)
        _parse_timestamp(self.created_at, "created_at")
        _validated_text(self.title, "title")
        _validated_text(self.message, "message")
        _validated_metadata(self.metadata)
        _assert_json_serializable(self.to_json_dict(), "alert intent")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "source_event_type": self.source_event_type,
            "source_event_reference": self.source_event_reference,
            "severity": self.severity,
            "channel": self.channel,
            "created_at": self.created_at,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> AlertIntent:
        expected_keys = {
            "schema_version",
            "alert_id",
            "source_event_type",
            "source_event_reference",
            "severity",
            "channel",
            "created_at",
            "title",
            "message",
            "metadata",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise AlertError("alert intent fields are invalid")
        metadata = raw_record["metadata"]
        if not isinstance(metadata, Mapping):
            raise AlertError("alert intent metadata must be an object")
        return cls(
            schema_version=raw_record["schema_version"],
            alert_id=raw_record["alert_id"],
            source_event_type=raw_record["source_event_type"],
            source_event_reference=raw_record["source_event_reference"],
            severity=raw_record["severity"],
            channel=raw_record["channel"],
            created_at=raw_record["created_at"],
            title=raw_record["title"],
            message=raw_record["message"],
            metadata=dict(metadata),
        )


@dataclass(frozen=True)
class AlertDispatchRequest:
    dispatch_id: str
    alert_id: str
    dispatched_at: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise AlertError("schema_version must be 1")
        _validated_identifier(self.dispatch_id, "dispatch_id")
        _validated_identifier(self.alert_id, "alert_id")
        _parse_timestamp(self.dispatched_at, "dispatched_at")
        _validated_text(self.reason, "reason")
        _assert_json_serializable(self.to_json_dict(), "alert dispatch request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dispatch_id": self.dispatch_id,
            "alert_id": self.alert_id,
            "dispatched_at": self.dispatched_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TelegramAlertPayload:
    api_method: str
    text: str
    disable_web_page_preview: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise AlertError("schema_version must be 1")
        if self.api_method != "sendMessage":
            raise AlertError("api_method must be sendMessage")
        _validated_text(self.text, "text")
        if not isinstance(self.disable_web_page_preview, bool):
            raise AlertError("disable_web_page_preview must be a boolean")
        _assert_json_serializable(self.to_json_dict(), "telegram alert payload")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "api_method": self.api_method,
            "text": self.text,
            "disable_web_page_preview": self.disable_web_page_preview,
        }


@dataclass(frozen=True)
class AlertDispatchOutcome:
    dispatch_id: str
    alert_id: str
    severity: str
    channel: str
    status: str
    dispatcher: str
    dispatched_at: str
    reason: str
    formatted_payload: dict[str, Any]
    alert: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise AlertError("schema_version must be 1")
        _validated_identifier(self.dispatch_id, "dispatch_id")
        _validated_identifier(self.alert_id, "alert_id")
        _validated_severity(self.severity)
        _validated_channel(self.channel)
        if self.status not in VALID_DISPATCH_STATUSES:
            raise AlertError("status must be one of recorded or failed")
        _validated_identifier(self.dispatcher, "dispatcher")
        _parse_timestamp(self.dispatched_at, "dispatched_at")
        _validated_text(self.reason, "reason")
        if not isinstance(self.formatted_payload, dict):
            raise AlertError("formatted_payload must be a JSON object")
        _validated_no_secret_shaped_content(self.formatted_payload, "formatted_payload")
        if not isinstance(self.alert, dict):
            raise AlertError("alert must be a JSON object")
        _validated_no_secret_shaped_content(self.alert, "alert")
        _assert_json_serializable(self.to_json_dict(), "alert dispatch outcome")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dispatch_id": self.dispatch_id,
            "alert_id": self.alert_id,
            "severity": self.severity,
            "channel": self.channel,
            "status": self.status,
            "dispatcher": self.dispatcher,
            "dispatched_at": self.dispatched_at,
            "reason": self.reason,
            "formatted_payload": self.formatted_payload,
            "alert": self.alert,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> AlertDispatchOutcome:
        expected_keys = {
            "schema_version",
            "dispatch_id",
            "alert_id",
            "severity",
            "channel",
            "status",
            "dispatcher",
            "dispatched_at",
            "reason",
            "formatted_payload",
            "alert",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise AlertError("alert dispatch outcome fields are invalid")
        formatted_payload = raw_record["formatted_payload"]
        alert = raw_record["alert"]
        if not isinstance(formatted_payload, Mapping) or not isinstance(alert, Mapping):
            raise AlertError("alert dispatch nested fields are invalid")
        typed_alert = AlertIntent.from_json_dict(alert)
        return cls(
            schema_version=raw_record["schema_version"],
            dispatch_id=raw_record["dispatch_id"],
            alert_id=raw_record["alert_id"],
            severity=raw_record["severity"],
            channel=raw_record["channel"],
            status=raw_record["status"],
            dispatcher=raw_record["dispatcher"],
            dispatched_at=raw_record["dispatched_at"],
            reason=raw_record["reason"],
            formatted_payload=dict(formatted_payload),
            alert=typed_alert.to_json_dict(),
        )


class AlertBook:
    def __init__(self, journal: JsonlEventJournal) -> None:
        self._journal = journal
        self._intent_requests: dict[str, dict[str, Any]] = {}
        self._intents: dict[str, AlertIntent] = {}
        self._dispatch_requests: dict[str, dict[str, Any]] = {}
        self._dispatch_outcomes: dict[str, AlertDispatchOutcome] = {}

    def create_intent(self, request: AlertIntentRequest) -> AlertIntent:
        if not isinstance(request, AlertIntentRequest):
            raise AlertError("request must be an AlertIntentRequest")

        request_payload = request.to_json_dict()
        if request.alert_id in self._intent_requests:
            if self._intent_requests[request.alert_id] != request_payload:
                raise AlertError("conflicting alert_id")
            return self._intents[request.alert_id]

        intent = AlertIntent.from_request(request)
        self._journal.append(
            event_type=ALERT_INTENT_CREATED_EVENT_TYPE,
            payload=intent.to_json_dict(),
            timestamp=intent.created_at,
        )
        self._intent_requests[request.alert_id] = request_payload
        self._intents[request.alert_id] = intent
        return intent

    def dispatch_alert(
        self,
        request: AlertDispatchRequest,
        dispatcher: AlertDispatcher,
    ) -> AlertDispatchOutcome:
        if not isinstance(request, AlertDispatchRequest):
            raise AlertError("request must be an AlertDispatchRequest")

        request_payload = request.to_json_dict()
        if request.dispatch_id in self._dispatch_requests:
            if self._dispatch_requests[request.dispatch_id] != request_payload:
                raise AlertError("conflicting dispatch_id")
            return self._dispatch_outcomes[request.dispatch_id]

        if request.alert_id not in self._intents:
            raise AlertError("unknown alert_id")

        outcome = dispatcher.dispatch(self._intents[request.alert_id], request)
        if not isinstance(outcome, AlertDispatchOutcome):
            raise AlertError("dispatcher must return an AlertDispatchOutcome")
        if outcome.dispatch_id != request.dispatch_id:
            raise AlertError("dispatcher returned mismatched dispatch_id")
        if outcome.alert_id != request.alert_id:
            raise AlertError("dispatcher returned mismatched alert_id")

        self._journal.append(
            event_type=ALERT_DISPATCH_RECORDED_EVENT_TYPE,
            payload=outcome.to_json_dict(),
            timestamp=outcome.dispatched_at,
        )
        self._dispatch_requests[request.dispatch_id] = request_payload
        self._dispatch_outcomes[request.dispatch_id] = outcome
        return outcome

    def current_intent(self, alert_id: str) -> AlertIntent:
        alert_id = _validated_identifier(alert_id, "alert_id")
        if alert_id not in self._intents:
            raise AlertError("unknown alert_id")
        return self._intents[alert_id]


class NoopAlertDispatcher:
    def dispatch(
        self,
        alert: AlertIntent,
        request: AlertDispatchRequest,
    ) -> AlertDispatchOutcome:
        if not isinstance(alert, AlertIntent):
            raise AlertError("alert must be an AlertIntent")
        if not isinstance(request, AlertDispatchRequest):
            raise AlertError("request must be an AlertDispatchRequest")

        formatted_payload = (
            format_telegram_alert(alert).to_json_dict()
            if alert.channel == "telegram"
            else _format_local_alert(alert)
        )
        return AlertDispatchOutcome(
            dispatch_id=request.dispatch_id,
            alert_id=alert.alert_id,
            severity=alert.severity,
            channel=alert.channel,
            status="recorded",
            dispatcher="noop",
            dispatched_at=request.dispatched_at,
            reason=request.reason,
            formatted_payload=formatted_payload,
            alert=alert.to_json_dict(),
        )


def format_telegram_alert(alert: AlertIntent) -> TelegramAlertPayload:
    if not isinstance(alert, AlertIntent):
        raise AlertError("alert must be an AlertIntent")
    if alert.channel != "telegram":
        raise AlertError("alert channel must be telegram")
    return TelegramAlertPayload(
        api_method="sendMessage",
        text=_format_alert_text(alert),
        disable_web_page_preview=True,
    )


def _format_local_alert(alert: AlertIntent) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "text": _format_alert_text(alert),
    }


def _format_alert_text(alert: AlertIntent) -> str:
    lines = [
        f"[{alert.severity.upper()}] {alert.title}",
        f"alert_id: {alert.alert_id}",
        f"source_event_type: {alert.source_event_type}",
        f"source_event_reference: {alert.source_event_reference}",
        f"created_at: {alert.created_at}",
        "",
        alert.message,
    ]
    if alert.metadata:
        lines.extend(["", "metadata:"])
        for key in sorted(alert.metadata):
            lines.append(f"- {key}: {_metadata_value_to_text(alert.metadata[key])}")
    text = "\n".join(lines)
    _validated_text(text, "text")
    return text


def _metadata_value_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _validated_severity(severity: str) -> str:
    if severity not in VALID_ALERT_SEVERITIES:
        raise AlertError("severity must be one of informational, warning, critical, or emergency")
    return severity


def _validated_channel(channel: str) -> str:
    if channel not in VALID_ALERT_CHANNELS:
        raise AlertError("channel must be one of local or telegram")
    return channel


def _validated_identifier(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlertError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise AlertError(f"{field_name} must not contain leading or trailing whitespace")
    _validated_no_secret_shaped_text(value, field_name)
    return value


def _validated_text(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlertError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise AlertError(f"{field_name} must not contain leading or trailing whitespace")
    _validated_no_secret_shaped_text(value, field_name)
    return value


def _validated_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise AlertError("metadata must be a JSON object")
    _validated_no_secret_shaped_content(metadata, "metadata")
    _assert_json_serializable(metadata, "metadata")
    return metadata


def _validated_no_secret_shaped_content(value: Any, field_name: str) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise AlertError(f"{field_name} keys must be strings")
            if _is_secret_shaped_key(key):
                raise AlertError(f"{field_name} must not contain secret-shaped field {key}")
            _validated_no_secret_shaped_content(nested_value, field_name)
        return
    if isinstance(value, list):
        for item in value:
            _validated_no_secret_shaped_content(item, field_name)
        return
    if isinstance(value, str):
        _validated_no_secret_shaped_text(value, field_name)


def _is_secret_shaped_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)


def _validated_no_secret_shaped_text(value: str, field_name: str) -> None:
    normalized = value.lower()
    if any(marker in normalized for marker in _SECRET_TEXT_MARKERS):
        raise AlertError(f"{field_name} must not contain credential-shaped text")


def _parse_timestamp(value: str | None, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AlertError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlertError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlertError(f"{field_name} must include a timezone")
    return parsed


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise AlertError(f"{payload_name} must be JSON-serializable") from exc
