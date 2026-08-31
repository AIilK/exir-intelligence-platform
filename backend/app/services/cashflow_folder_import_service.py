from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService


class CashflowFolderImportService:
    """Import new daily cash-flow workbooks from a configured local folder."""

    def __init__(self) -> None:
        self.inbox = Path(settings.cashflow_excel_inbox)
        self.archive = Path(settings.cashflow_excel_archive)
        self.state_path = Path(settings.cashflow_excel_state_file)
        self.cashflow = MonthlyCashflowExcelService()
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.archive.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _state(self) -> dict[str, Any]:
        empty = {
            "last_scan_at": None,
            "last_success_at": None,
            "last_successful_file": None,
            "last_error": None,
            "processed_hashes": {},
        }
        if not self.state_path.exists():
            return empty
        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
            return {**empty, **loaded}
        except (OSError, ValueError, json.JSONDecodeError):
            return empty

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def scan(self) -> dict[str, Any]:
        state = self._state()
        processed = state.setdefault("processed_hashes", {})
        imported: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []
        now = datetime.now(timezone.utc)

        for source in sorted(
            self.inbox.glob("*.xlsx"),
            key=lambda item: item.stat().st_mtime,
        ):
            try:
                # Avoid opening a workbook while Windows is still copying it.
                age_seconds = datetime.now().timestamp() - source.stat().st_mtime
                if age_seconds < settings.cashflow_excel_min_file_age_seconds:
                    skipped.append({"filename": source.name, "reason": "file_is_still_new"})
                    continue

                fingerprint = self._hash(source)
                if fingerprint in processed:
                    skipped.append({"filename": source.name, "reason": "duplicate_content"})
                    continue

                result = self.cashflow.save_upload(source, source.name)
                snapshot = result.get("snapshot") or {}
                archive_name = (
                    f"{str(snapshot.get('jalali_date') or 'unknown').replace('/', '')}"
                    f"__{fingerprint[:8]}__{source.name}"
                )
                archive_target = self.archive / archive_name
                shutil.move(str(source), str(archive_target))

                item = {
                    "filename": source.name,
                    "archive_file": archive_target.name,
                    "jalali_date": snapshot.get("jalali_date"),
                    "liquidity_rial": snapshot.get("liquidity_rial"),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
                processed[fingerprint] = item
                imported.append(item)
                state["last_success_at"] = item["processed_at"]
                state["last_successful_file"] = item
                state["last_error"] = None
            except Exception as exc:
                error = {"filename": source.name, "error": str(exc)}
                errors.append(error)
                state["last_error"] = error

        state["last_scan_at"] = now.isoformat()
        self._save_state(state)
        return {
            "status": "success" if not errors else "partial_success",
            "enabled": settings.cashflow_excel_scan_enabled,
            "inbox": str(self.inbox),
            "archive": str(self.archive),
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "last_scan_at": state["last_scan_at"],
            "last_success_at": state["last_success_at"],
            "last_successful_file": state["last_successful_file"],
        }

    def status(self) -> dict[str, Any]:
        state = self._state()
        waiting = []
        if self.inbox.exists():
            waiting = [item.name for item in sorted(self.inbox.glob("*.xlsx"))]
        return {
            "status": "ready" if settings.cashflow_excel_scan_enabled else "disabled",
            "enabled": settings.cashflow_excel_scan_enabled,
            "inbox": str(self.inbox),
            "archive": str(self.archive),
            "scan_minutes": settings.cashflow_excel_scan_minutes,
            "waiting_count": len(waiting),
            "waiting_files": waiting[:20],
            "last_scan_at": state.get("last_scan_at"),
            "last_success_at": state.get("last_success_at"),
            "last_successful_file": state.get("last_successful_file"),
            "last_error": state.get("last_error"),
        }
