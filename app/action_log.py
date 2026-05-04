from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


_LOCK = Lock()


def log_action(action: str, **payload: object) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "action": action,
        **payload,
    }
    targets = [_resolve_log_path()]
    fallback_path = Path(tempfile.gettempdir()) / "workua-outreach-actions.log"
    if fallback_path not in targets:
        targets.append(fallback_path)

    with _LOCK:
        payload_text = json.dumps(event, ensure_ascii=False) + "\n"
        for path in targets:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(payload_text)
                return
            except OSError:
                continue


def _resolve_log_path() -> Path:
    configured = os.getenv("ACTION_LOG_PATH")
    if configured:
        return Path(configured)
    return Path("data/actions.log")
