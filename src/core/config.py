from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str = "sqlite+aiosqlite:///./multi_agent.db"
    database_url_production: str = "postgresql+asyncpg://user:pass@localhost:5432/multi_agent"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent
    agents_root: Path = project_root / "agents"
    workspace_dir_name: str = "workspace"
    soul_filename: str = "soul.md"
    memory_filename: str = "memory.md"

    # LiteLLM
    litellm_drop_params: bool = True
    litellm_default_max_retries: int = 3
    litellm_default_retry_delay: float = 2.0
    litellm_default_timeout: int = 120

    # Security
    fernet_key: str = ""  # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # Email (for Communications Agent)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    user_email: str = ""  # Where daily briefings are sent

    # Meeting defaults
    meeting_max_turns_default: int = 50
    meeting_max_duration_minutes_default: int = 60
    meeting_request_to_speak_timeout_seconds: int = 10
    meeting_poll_timeout_per_agent_seconds: int = 30
    meeting_stalemate_similarity_threshold: float = 0.85
    meeting_stalemate_consecutive_rounds: int = 3

    # Task defaults
    task_max_retries_default: int = 3
    task_max_escalation_depth: int = 3
    task_escalation_cooldown_minutes: int = 15
    task_max_subtask_depth: int = 3

    # Memory
    agent_max_memory_tokens_default: int = 100000
    agent_memory_prune_threshold: float = 0.1

    # Platform
    platform_name: str = "Multi-Agent Platform"
    debug: bool = False


settings = Settings()
