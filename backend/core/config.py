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

    # =====================================================
    # OPENAI
    # =====================================================

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"
    treasury_agent_max_turns: int = 6
    treasury_agent_session_db: str = "./treasury_agent_sessions.db"
    treasury_reconciliation_db: str = "./treasury_reconciliation.db"
    treasury_operational_currency_ref: int = 1
    treasury_operational_currency_name: str = "ریال"
    financial_query_max_rows: int = 200
    financial_query_timeout_seconds: int = 20
    customer_intelligence_scheduler_enabled: bool = True
    customer_intelligence_daily_hour: int = 7
    customer_intelligence_daily_minute: int = 0
    customer_intelligence_history_db: str = "./customer_intelligence_history.db"
    customer_representative_mapping_file: str = "./data/customer_representative_mapping.csv"
    customer_behavior_agent_enabled: bool = True
    customer_behavior_agent_model: str = ""
    customer_behavior_agent_max_customers: int = 25

    # =====================================================
    # SETTINGS
    # =====================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
