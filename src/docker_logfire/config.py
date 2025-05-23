"""Configuration settings for docker-logfire."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Logfire settings
    logfire_token: str = Field(..., description="Logfire API token")
    service_name: str = Field(default="docker-logfire", description="Service name for Logfire logs")

    # Docker settings
    docker_socket: str = Field(default="/var/run/docker.sock", description="Path to Docker socket")

    # Container filtering  
    exclude_containers: str = Field(
        default="docker-logfire",
        description="Comma-separated container names to exclude from log collection",
    )
    include_stopped: bool = Field(default=False, description="Include logs from stopped containers")

    # Logging settings
    log_level: str = Field(default="INFO", description="Application log level")

    def get_exclude_containers(self) -> list[str]:
        """Get list of containers to exclude."""
        if not self.exclude_containers:
            return []
        return [name.strip() for name in self.exclude_containers.split(",") if name.strip()]
