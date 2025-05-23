"""Forward container logs to Logfire."""

import json
import logging
from typing import Any

import logfire
from docker.models.containers import Container

from .config import Settings

logger = logging.getLogger(__name__)


class LogForwarder:
    """Forwards container logs to Logfire with proper service attribution."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the log forwarder and configure Logfire."""
        self.settings = settings

        # Configure default Logfire for docker-logfire itself
        logfire.configure(
            token=settings.logfire_token,
            service_name="docker-logfire",
            send_to_logfire=True,
        )

        # Store per-container logfire instances
        self.container_loggers: dict[str, Any] = {}

    def get_container_logger(self, container_name: str) -> Any:
        """Get or create a Logfire logger for a specific container."""
        if container_name not in self.container_loggers:
            # Create a new Logfire instance with the container name as the service name
            container_logfire = logfire.configure(
                local=True,
                service_name=container_name,
                token=self.settings.logfire_token,
                send_to_logfire=True,
            )
            self.container_loggers[container_name] = container_logfire
            logger.info(f"Created Logfire logger for container: {container_name}")

        return self.container_loggers[container_name]

    def parse_docker_log(self, log_line: bytes) -> tuple[str, dict[str, Any]]:
        """Parse Docker log line and extract message and metadata."""
        try:
            # Docker logs come as bytes, decode them
            log_str = log_line.decode("utf-8").strip()

            # Try to parse as JSON (common for structured logs)
            try:
                log_data = json.loads(log_str)
                if isinstance(log_data, dict):
                    # Extract message if it exists
                    message = log_data.pop("message", log_str)
                    return message, log_data
                else:
                    return log_str, {}
            except json.JSONDecodeError:
                # Plain text log
                return log_str, {}

        except Exception as e:
            logger.error(f"Failed to parse log line: {e}")
            return str(log_line), {"parse_error": str(e)}

    async def stream_container_logs(self, container: Container) -> None:
        """Stream logs from a container to Logfire."""
        container_name = container.name.lstrip("/") if container.name else container.short_id
        container_logger = self.get_container_logger(container_name)

        logger.info(f"Starting log stream for container: {container_name}")

        try:
            # Get log stream from container
            log_stream = container.logs(
                stream=True,
                follow=True,
                timestamps=True,
                tail=100,  # Start with last 100 lines
            )

            for log_line in log_stream:
                if log_line:
                    # Parse the log line
                    message, extra_data = self.parse_docker_log(log_line)

                    # Add container metadata
                    container_image = "unknown"
                    if container.image and container.image.tags:
                        container_image = container.image.tags[0]

                    log_data = {
                        "container_id": container.short_id,
                        "container_name": container_name,
                        "container_image": container_image,
                        **extra_data,
                    }

                    # Send to Logfire
                    container_logger.info(message, **log_data)

        except Exception as e:
            logger.error(f"Error streaming logs for container {container_name}: {e}")
            raise

    async def handle_container_event(self, event: dict[str, Any]) -> None:
        """Handle container lifecycle events."""
        container_name = event.get("Actor", {}).get("Attributes", {}).get("name", "unknown")
        status = event.get("status", "unknown")

        # Log the event itself
        logfire.info(
            f"Container {status}: {container_name}",
            event_type="container_lifecycle",
            container_name=container_name,
            status=status,
            container_id=event.get("id", "")[:12],
        )
