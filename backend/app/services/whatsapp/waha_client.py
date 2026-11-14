"""کلاینت ساده WAHA (WhatsApp HTTP API) بدون وابستگی اضافه (urllib).

مسیرها مطابق مستندات WAHA:
  POST /api/sendText, POST /api/sendFile, GET /api/contacts/check-exists
  GET/POST /api/sessions..., GET /api/{session}/auth/qr
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import settings

_PERSIAN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class WahaError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def normalize_mobile(raw: Any) -> str | None:
    """شماره موبایل ایران را به شکل 989xxxxxxxxx برمی‌گرداند؛ تلفن ثابت یا شماره نامعتبر ← None."""
    digits = re.sub(r"\D", "", str(raw or "").translate(_PERSIAN))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits.startswith("9"):
        return "98" + digits
    return None


def chat_id(phone: str) -> str:
    return f"{phone}@c.us"


class WahaClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, session: str | None = None, timeout: int = 60):
        self.base_url = (base_url or settings.waha_url).rstrip("/")
        self.api_key = settings.waha_api_key if api_key is None else api_key
        self.session = session or settings.waha_session
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None, accept: str = "application/json") -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        req.add_header("Accept", accept)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("X-Api-Key", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise WahaError(f"WAHA {exc.code}: {detail}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WahaError(f"WAHA در دسترس نیست ({self.base_url}): {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode("utf-8", "replace")

    # ---------- نشست ----------
    def session_info(self) -> dict[str, Any] | None:
        try:
            return self._call("GET", f"/api/sessions/{urllib.parse.quote(self.session)}")
        except WahaError as exc:
            if exc.status == 404:
                return None
            raise

    def start_session(self) -> Any:
        if self.session_info() is None:
            return self._call("POST", "/api/sessions", {"name": self.session, "start": True})
        return self._call("POST", f"/api/sessions/{urllib.parse.quote(self.session)}/start", {})

    def logout(self) -> Any:
        return self._call("POST", f"/api/sessions/{urllib.parse.quote(self.session)}/logout", {})

    def qr(self) -> dict[str, Any]:
        """{"mimetype": "image/png", "data": "<base64>"}"""
        return self._call("GET", f"/api/{urllib.parse.quote(self.session)}/auth/qr?format=image")

    # ---------- ارسال ----------
    def check_exists(self, phone: str) -> str | None:
        """chatId واقعی واتساپ این شماره؛ اگر شماره واتساپ ندارد None."""
        q = urllib.parse.urlencode({"phone": phone, "session": self.session})
        res = self._call("GET", f"/api/contacts/check-exists?{q}") or {}
        if not res.get("numberExists"):
            return None
        return res.get("chatId") or chat_id(phone)

    def send_text(self, to_chat_id: str, text: str) -> Any:
        return self._call("POST", "/api/sendText", {"session": self.session, "chatId": to_chat_id, "text": text})

    def send_file(self, to_chat_id: str, content: bytes, filename: str, caption: str = "", mimetype: str = XLSX_MIME) -> Any:
        return self._call("POST", "/api/sendFile", {
            "session": self.session, "chatId": to_chat_id, "caption": caption,
            "file": {"mimetype": mimetype, "filename": filename, "data": base64.b64encode(content).decode("ascii")},
        })
