from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class ArtifactSet:
    request_dir: Path
    screenshot_path: Path
    html_snapshot_path: Path
    trace_path: Path
    request_log_path: Path


class DiagnosticStore:
    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root
        self._artifact_root.mkdir(parents=True, exist_ok=True)

    def create(self, request_id: str) -> ArtifactSet:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        request_dir = self._artifact_root / f"{stamp}-{request_id}"
        request_dir.mkdir(parents=True, exist_ok=True)
        return ArtifactSet(
            request_dir=request_dir,
            screenshot_path=request_dir / "failure.png",
            html_snapshot_path=request_dir / "page.html",
            trace_path=request_dir / "trace.zip",
            request_log_path=request_dir / "request.log",
        )
