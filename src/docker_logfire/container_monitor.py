"""Monitor Docker containers and their lifecycle events."""

import asyncio
import logging
from typing import Any

import docker
from docker.errors import DockerException
from docker.models.containers import Container

from .config import Settings

logger = logging.getLogger(__name__)


class ContainerMonitor:
    """Monitors Docker containers and manages their lifecycle."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the container monitor."""
        self.settings = settings
        self.client = docker.DockerClient(base_url=f"unix://{settings.docker_socket}")
        self.active_containers: set[str] = set()

    def get_container_name(self, container: Container) -> str:
        """Extract container name without leading slash."""
        if container.name:
            return container.name.lstrip("/")
        return container.short_id

    def should_monitor_container(self, container: Container) -> bool:
        """Check if container should be monitored based on settings."""
        container_name = self.get_container_name(container)

        # Check exclusion list
        if container_name in self.settings.get_exclude_containers():
            logger.debug(f"Skipping excluded container: {container_name}")
            return False

        # Check container status
        if container.status != "running" and not self.settings.include_stopped:
            logger.debug(
                f"Skipping non-running container: {container_name} (status: {container.status})"
            )
            return False

        return True

    def list_containers(self) -> list[Container]:
        """List all containers that should be monitored."""
        try:
            containers = self.client.containers.list(all=self.settings.include_stopped)
            monitored = [c for c in containers if self.should_monitor_container(c)]

            logger.info(
                f"Found {len(monitored)} containers to monitor out of {len(containers)} total"
            )
            for container in monitored:
                logger.debug(f"Will monitor container: {self.get_container_name(container)}")

            return monitored
        except DockerException as e:
            logger.error(f"Failed to list containers: {e}")
            return []

    async def watch_events(self, event_callback: Any) -> None:
        """Watch for container lifecycle events."""
        logger.info("Starting container event monitor")

        try:
            # Watch for container events in a separate thread
            for event in self.client.events(filters={"type": "container"}, decode=True):  # type: ignore[no-untyped-call]
                if event.get("status") in ["start", "stop", "die"]:
                    container_id = event.get("id", "")[:12]
                    container_name = (
                        event.get("Actor", {}).get("Attributes", {}).get("name", "unknown")
                    )
                    status = event.get("status")

                    logger.info(f"Container event: {container_name} ({container_id}) - {status}")

                    # Notify callback about the event
                    await asyncio.create_task(event_callback(event))

        except Exception as e:
            logger.error(f"Error watching container events: {e}")
            raise
