"""Main entry point for docker-logfire."""

import asyncio
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import logfire
from docker.models.containers import Container

from .config import Settings
from .container_monitor import ContainerMonitor
from .log_forwarder import LogForwarder

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DockerLogfire:
    """Main application class that orchestrates container monitoring and log forwarding."""

    def __init__(self) -> None:
        """Initialize the application."""
        self.settings = Settings()  # type: ignore[call-arg]
        self.monitor = ContainerMonitor(self.settings)
        self.forwarder = LogForwarder(self.settings)
        self.active_tasks: set[asyncio.Task[Any]] = set()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.running = True

        # Set logging level
        logging.getLogger().setLevel(self.settings.log_level)

    async def handle_container_event(self, event: dict[str, Any]) -> None:
        """Handle container lifecycle events."""
        status = event.get("status")
        container_id = event.get("id", "")[:12]

        await self.forwarder.handle_container_event(event)

        if status == "start":
            # Start monitoring new container
            try:
                container = self.monitor.client.containers.get(container_id)
                if self.monitor.should_monitor_container(container):
                    task = asyncio.create_task(self.monitor_container_with_retry(container))
                    self.active_tasks.add(task)
                    task.add_done_callback(self.active_tasks.discard)
            except Exception as e:
                logger.error(f"Failed to start monitoring container {container_id}: {e}")

        elif status in ["stop", "die"]:
            # Container stopped, log stream will end naturally
            pass
    
    async def monitor_container_with_retry(self, container: Container, max_retries: int = 3) -> None:
        """Monitor container logs with retry logic."""
        container_name = container.name.lstrip("/") if container.name else container.short_id
        retry_count = 0
        base_delay = 1  # Start with 1 second
        
        while retry_count < max_retries and self.running:
            try:
                await self.forwarder.stream_container_logs(container)
                # If we reach here, streaming ended normally (container stopped)
                break
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    delay = base_delay * (2 ** retry_count)  # Exponential backoff
                    logger.warning(
                        f"Log streaming failed for {container_name}, retrying in {delay}s "
                        f"(attempt {retry_count}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Failed to stream logs for {container_name} after {max_retries} attempts")

    async def monitor_existing_containers(self) -> None:
        """Start monitoring all existing containers."""
        containers = self.monitor.list_containers()

        for container in containers:
            if self.running:
                container_name = container.name.lstrip("/") if container.name else container.short_id
                logger.info(f"Creating monitoring task for container: {container_name}")
                task = asyncio.create_task(self.monitor_container_with_retry(container))
                self.active_tasks.add(task)
                task.add_done_callback(self.active_tasks.discard)

    async def run_event_monitor(self) -> None:
        """Run the event monitor."""
        await self.monitor.watch_events(self.handle_container_event)

    async def run(self) -> None:
        """Run the main application loop."""
        logger.info("Starting Docker Logfire")
        logfire.info("Docker Logfire started", version="0.1.0")

        try:
            # Start monitoring existing containers
            await self.monitor_existing_containers()

            # Start watching for new container events
            event_task = asyncio.create_task(self.run_event_monitor())

            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(1)

            # Cancel event monitoring
            event_task.cancel()

            # Wait for all active tasks to complete
            if self.active_tasks:
                logger.info(f"Waiting for {len(self.active_tasks)} active tasks to complete...")
                await asyncio.gather(*self.active_tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            self.executor.shutdown(wait=True)
            logger.info("Docker Logfire stopped")

    def shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False


def main() -> None:
    """Main entry point."""
    app = DockerLogfire()

    # Set up signal handlers
    signal.signal(signal.SIGINT, app.shutdown)
    signal.signal(signal.SIGTERM, app.shutdown)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
