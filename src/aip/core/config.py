from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIP_", env_file=".env", extra="ignore")

    # SQLite works with zero setup; docker-compose sets the Postgres URL.
    database_url: str = "sqlite+aiosqlite:///./aip.db"
    # Tests and the demo create tables on startup; deployments run `alembic upgrade head`
    # and set this to false.
    auto_create_schema: bool = True
    sql_echo: bool = False
    document_dir: str = "var/documents"
    # Delay before a claim with a new document is processed, so several uploads in a row
    # produce one pipeline run.
    job_debounce_seconds: float = 2.0
