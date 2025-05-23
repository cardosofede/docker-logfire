"""Main entry point for docker-logfire."""

import asyncio
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import logfire

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
        self.settings = Settings()
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
                    task = asyncio.create_task(self.forwarder.stream_container_logs(container))
                    self.active_tasks.add(task)
                    task.add_done_callback(self.active_tasks.discard)
            except Exception as e:
                logger.error(f"Failed to start monitoring container {container_id}: {e}")

        elif status in ["stop", "die"]:
            # Container stopped, log stream will end naturally
            pass

    async def monitor_existing_containers(self) -> None:
        """Start monitoring all existing containers."""
        containers = self.monitor.list_containers()

        for container in containers:
            if self.running:
                task = asyncio.create_task(self.forwarder.stream_container_logs(container))
                self.active_tasks.add(task)
                task.add_done_callback(self.active_tasks.discard)

    async def run_event_monitor(self) -> None:
        """Run the event monitor in a thread to avoid blocking."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self.executor,
            lambda: asyncio.run(self.monitor.watch_events(self.handle_container_event)),
        )

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
