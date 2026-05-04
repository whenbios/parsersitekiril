from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


_LOCK = Lock()


def log_action(action: str, **payload: object) -> None:
    path = Path(os.getenv("ACTION_LOG_PATH", "data/actions.log"))
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "action": action,
        **payload,
    }
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
