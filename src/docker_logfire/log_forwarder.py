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

        # Configure Logfire with the configurable service name
        logfire.configure(
            token=settings.logfire_token,
            service_name=settings.service_name,
            send_to_logfire=True,
        )


    def parse_docker_log(self, log_line: bytes) -> tuple[str, dict[str, Any]]:
        """Parse Docker log line and extract message and metadata."""
        try:
            # Docker logs come as bytes, decode them
            log_str = log_line.decode("utf-8").strip()
            
            # When using timestamps=True, Docker prepends RFC3339 timestamp
            # Format: 2025-05-23T20:03:59.691483928Z <actual log>
            timestamp = None
            if log_str and len(log_str) > 30 and log_str[4] == '-' and log_str[19] == 'T':
                # Extract timestamp and actual log message
                parts = log_str.split(' ', 1)
                if len(parts) == 2:
                    timestamp = parts[0]
                    log_str = parts[1]

            # Try to parse as JSON (common for structured logs)
            try:
                log_data = json.loads(log_str)
                if isinstance(log_data, dict):
                    # Extract message if it exists
                    message = log_data.pop("message", log_str)
                    if timestamp:
                        log_data["docker_timestamp"] = timestamp
                    return message, log_data
                else:
                    extra_data = {"docker_timestamp": timestamp} if timestamp else {}
                    return log_str, extra_data
            except json.JSONDecodeError:
                # Plain text log
                extra_data = {"docker_timestamp": timestamp} if timestamp else {}
                return log_str, extra_data

        except Exception as e:
            logger.error(f"Failed to parse log line: {e}")
            return str(log_line), {"parse_error": str(e)}

    async def stream_container_logs(self, container: Container) -> None:
        """Stream logs from a container to Logfire."""
        container_name = container.name.lstrip("/") if container.name else container.short_id
        
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
                    try:
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

                        # Send to Logfire with container name in the data
                        logfire.info(message, **log_data)
                    except Exception as e:
                        # Log error but continue processing
                        logfire.error(f"Error processing log line for {container_name}: {e}")

        except Exception as e:
            logger.error(f"Error streaming logs for container {container_name}: {e}")
            # Don't re-raise - let the task end gracefully
        finally:
            logfire.info(f"Log stream ended for container: {container_name}")

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
