import logging
import secrets
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from app.core.config import settings


logger = logging.getLogger(__name__)


class TreasuryAgentConfigurationError(RuntimeError):
    pass


class TreasuryAgentRateLimitError(RuntimeError):
    pass


class TreasuryAgentTimeoutError(RuntimeError):
    pass


class TreasuryAgentExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TreasuryChatResult:
    answer: str
    session_id: str


def get_treasury_agent_status() -> dict[str, object]:
    """تنظیمات و بارگذاری Agent را بدون مصرف اعتبار API بررسی می‌کند."""

    diagnostics: dict[str, str] = {}
    key_is_configured = bool(settings.openai_api_key.strip())
    diagnostics["api_key"] = "configured" if key_is_configured else "missing"

    try:
        diagnostics["openai_agents_version"] = version("openai-agents")
    except PackageNotFoundError:
        diagnostics["openai_agents_version"] = "not-installed"

    agent_loads = False
    try:
        from agents import Runner, SQLiteSession  # noqa: F401
        from app.agents.treasury_agent import treasury_agent  # noqa: F401

        agent_loads = True
        diagnostics["agent_import"] = "ok"
    except Exception as exc:
        diagnostics["agent_import"] = f"failed:{type(exc).__name__}"
        logger.exception("Treasury Agent status import check failed")

    ready = key_is_configured and agent_loads
    return {
        "status": "success",
        "ready": ready,
        "model": settings.openai_model,
        "message": (
            "Agent برای دریافت سؤال آماده است."
            if ready
            else "Agent آماده نیست؛ بخش diagnostics را بررسی کنید."
        ),
        "diagnostics": diagnostics,
    }


def _raise_friendly_agent_error(exc: Exception) -> None:
    """خطاهای متداول SDK را بدون افشای جزئیات حساس قابل‌فهم می‌کند."""

    error_name = type(exc).__name__.lower()
    error_text = str(exc).lower()

    if "authentication" in error_name or "invalid api key" in error_text:
        raise TreasuryAgentConfigurationError(
            "کلید OpenAI معتبر نیست؛ مقدار OPENAI_API_KEY را در .env بررسی کنید."
        ) from exc
    if "permission" in error_name:
        raise TreasuryAgentConfigurationError(
            "این کلید به مدل تنظیم‌شده دسترسی ندارد؛ OPENAI_MODEL را بررسی کنید."
        ) from exc
    if "ratelimit" in error_name or "insufficient_quota" in error_text:
        raise TreasuryAgentRateLimitError(
            "اعتبار یا محدودیت مصرف OpenAI اجازه اجرای درخواست را نداد."
        ) from exc
    if "timeout" in error_name:
        raise TreasuryAgentTimeoutError(
            "پاسخ OpenAI بیش از حد طول کشید؛ دوباره تلاش کنید."
        ) from exc
    raise TreasuryAgentExecutionError(
        "اجرای Agent خزانه با خطای پیش‌بینی‌نشده مواجه شد."
    ) from exc


async def run_treasury_chat(
    message: str,
    session_id: str | None = None,
) -> TreasuryChatResult:
    """سؤال را با حافظه مکالمه به Treasury Agent می‌دهد."""

    cleaned_message = message.strip()
    if not cleaned_message:
        raise ValueError("پیام نمی‌تواند خالی باشد.")

    if not settings.openai_api_key:
        raise TreasuryAgentConfigurationError(
            "OPENAI_API_KEY در فایل .env تنظیم نشده است."
        )

    try:
        from agents import Runner, SQLiteSession, set_default_openai_key
    except ImportError as exc:
        raise TreasuryAgentConfigurationError(
            "بسته openai-agents نصب نشده است؛ "
            "دستور pip install openai-agents را اجرا کنید."
        ) from exc
    except Exception as exc:
        logger.exception("OpenAI Agents SDK could not be imported")
        python_version = ".".join(map(str, sys.version_info[:3]))
        raise TreasuryAgentConfigurationError(
            "بارگذاری openai-agents ناموفق بود "
            f"({type(exc).__name__}, Python {python_version}). "
            "محیط مجازی را با Python 3.12 دوباره بسازید."
        ) from exc

    try:
        from app.agents.treasury_agent import treasury_agent
    except Exception as exc:
        logger.exception("Treasury Agent could not be imported")
        raise TreasuryAgentExecutionError(
            f"ساخت Agent ناموفق بود ({type(exc).__name__})؛ "
            "جزئیات در ترمینال uvicorn ثبت شده است."
        ) from exc

    active_session_id = session_id or secrets.token_urlsafe(18)

    try:
        set_default_openai_key(settings.openai_api_key)
        session = SQLiteSession(
            active_session_id,
            settings.treasury_agent_session_db,
        )
        result = await Runner.run(
            treasury_agent,
            cleaned_message,
            max_turns=settings.treasury_agent_max_turns,
            session=session,
        )
    except Exception as exc:
        logger.exception("Treasury Agent execution failed")
        _raise_friendly_agent_error(exc)

    return TreasuryChatResult(
        answer=str(result.final_output),
        session_id=active_session_id,
    )
