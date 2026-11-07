from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # =====================================================
    # DATABASE
    # =====================================================

    DATABASE_URL: str = "sqlite:///./exir.db"

    # SQL Server راهکاران. رمز عبور فقط از فایل .env خوانده می‌شود.
    SQLSERVER_SERVER: str = "SERVER2016\\SQL2017"
    SQLSERVER_DATABASE: str = "Exir_sg3"
    SQLSERVER_USERNAME: str = "Ai"
    SQLSERVER_PASSWORD: str = ""
    SQLSERVER_DRIVER: str = "ODBC Driver 18 for SQL Server"
    SQLSERVER_TRUST_CERTIFICATE: bool = True

    # Live Karamad SQL Server. Defaults match the current Karamad installation
    # discovered during the live database inspection; keep these configurable.
    KARAMAD_SQLSERVER_SERVER: str = "SERVER2016\\SQL2017"
    KARAMAD_SQLSERVER_DATABASE: str = "KDB"
    KARAMAD_SQLSERVER_USERNAME: str = "Ai"
    KARAMAD_SQLSERVER_PASSWORD: str = ""
    KARAMAD_SQLSERVER_DRIVER: str = "ODBC Driver 18 for SQL Server"
    KARAMAD_SQLSERVER_TRUST_CERTIFICATE: bool = True

    # =====================================================
    # OPENAI
    # =====================================================

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"
    treasury_reconciliation_db: str = "./treasury_reconciliation.db"
    # Shared only between the trusted frontend proxy and Backend. Never expose
    # this value in NEXT_PUBLIC_* variables or browser code.
    reconciliation_api_key: str = ""
    # ورود کاربران و سطح دسترسی ماژول‌ها (app/auth). false فقط برای اجرای محلی بدون ورود.
    auth_enabled: bool = True
    payment_commitment_review_file: str = "./data/payment_commitment_reviews.json"
    treasury_operational_currency_ref: int = 1
    treasury_operational_currency_name: str = "ریال"
    # Comma-separated PayableNote.State codes confirmed by finance as cleared.
    # Example only after verification in this Rahkaran installation: "15,28"
    treasury_issued_paid_states: str = "28"
    customer_intelligence_scheduler_enabled: bool = True
    customer_intelligence_daily_hour: int = 7
    customer_intelligence_daily_minute: int = 0
    # گزارش هفتگی ریسک هیبریدها (app/services/hybrid_risk_service.py): شنبه ساعت ۷:۳۰ صبح
    hybrid_risk_weekly_enabled: bool = True
    hybrid_risk_weekly_day: str = "sat"
    hybrid_risk_weekly_hour: int = 7
    hybrid_risk_weekly_minute: int = 30
    # تحلیل هوشمند پرونده هیبریدها و نمایندگان راهکاران از روی تاریخچه (app/services/ai_file_analysis_service.py):
    # هفتگی بعد از گزارش ریسک (شنبه ۸ صبح)، فقط پرونده‌هایی که تاریخچه‌شان عوض شده. مدل خالی = همان openai_model.
    ai_file_analysis_enabled: bool = True
    ai_file_analysis_model: str = ""
    ai_file_analysis_weekly_hour: int = 8
    ai_file_analysis_weekly_minute: int = 0
    customer_intelligence_history_db: str = "./customer_intelligence_history.db"
    customer_representative_mapping_file: str = "./data/customer_representative_mapping.csv"
    # Four recurring KarAmand exports. The folder and its four subfolders are
    # created automatically on Backend startup/first scan.
    karamad_excel_inbox: str = "KaramadInbox"
    karamad_excel_archive: str = "KaramadArchive"
    karamad_excel_state_file: str = "backend/data/karamad_manual/state.json"
    karamad_excel_scan_enabled: bool = True
    karamad_excel_scan_minutes: int = 15
    karamad_excel_min_file_age_seconds: int = 30

    # =====================================================
    # SETTINGS
    # =====================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
