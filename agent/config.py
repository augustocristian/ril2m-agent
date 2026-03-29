"""Configuration for the RIL2M agent."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"

    # GitHub
    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""
    github_base_branch: str = "main"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "annotated_tests"

    # Logging
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
