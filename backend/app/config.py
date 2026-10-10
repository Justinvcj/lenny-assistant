"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM & Embedding Settings
    llM_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://host.docker.internal:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Optional Anthropic Cloud Key
    anthropic_api_key: str = ""

    # Database Settings
    database_url: str = "postgresql+psycopg://postgres:localdev@db:5432/lenny_assistant"

    # RAG & Agent Settings
    retrieval_top_k: int = 6
    retrieval_min_score: float = 0.5
    history_turns: int = 6
    agent_timeout_s: int = 120
    artifact_max_bytes: int = 200000

    # CORS & Application Settings
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    data_dir: str = "/data"
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
