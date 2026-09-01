from __future__ import annotations

import os
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ServiceLogEntry:
    sequence: int
    timestamp: str
    level: str
    source: str
    message: str
    context: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ServiceLogBuffer:
    """Small process-local structured log buffer for the operator WebUI."""

    def __init__(self, capacity: int = 1000) -> None:
        self.capacity = max(100, capacity)
        self.instance_id = uuid.uuid4().hex
        self._entries: deque[ServiceLogEntry] = deque(maxlen=self.capacity)
        self._sequence = 0
        self._lock = threading.Lock()

    def emit(
        self,
        level: str,
        source: str,
        message: str,
        **context: Any,
    ) -> ServiceLogEntry:
        with self._lock:
            self._sequence += 1
            entry = ServiceLogEntry(
                sequence=self._sequence,
                timestamp=utc_now_iso(),
                level=level.lower(),
                source=source,
                message=message,
                context=context,
            )
            self._entries.append(entry)
            return entry

    def read(self, *, after: int = 0, limit: int = 200) -> dict[str, Any]:
        safe_limit = max(1, min(limit, 500))
        with self._lock:
            entries = list(self._entries)
            if after > 0:
                selected = [entry for entry in entries if entry.sequence > after][
                    :safe_limit
                ]
            else:
                selected = entries[-safe_limit:]
            return {
                "instance_id": self.instance_id,
                "items": [entry.as_dict() for entry in selected],
                "latest_sequence": self._sequence,
                "capacity": self.capacity,
            }


service_logs = ServiceLogBuffer(
    capacity=int(os.getenv("SERVICE_LOG_CAPACITY", "1000"))
)
