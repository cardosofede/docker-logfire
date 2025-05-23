# docker-logfire

A Docker container that streams logs from other containers on the same machine to [Logfire](https://pydantic.dev/logfire) for centralized log management.

## Overview

docker-logfire runs as a Docker container alongside your other services and automatically:
- Discovers running containers on the same Docker host
- Streams their logs in real-time
- Uses container names as service names in Logfire
- Provides centralized log aggregation and monitoring

## Features

- **Automatic Container Discovery**: Detects all running containers on the Docker host
- **Real-time Log Streaming**: Captures and forwards logs as they're generated
- **Service Name Mapping**: Maps container names to Logfire service names for easy identification
- **Low Overhead**: Minimal resource usage, designed to run alongside your services
- **Docker Native**: Uses Docker API for reliable log collection

## Quick Start

### Build the Image

```bash
docker build -t docker-logfire:latest .
```

### Run with Docker

```bash
docker run -d \
  --name docker-logfire \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -e LOGFIRE_TOKEN=your-logfire-token \
  docker-logfire:latest
```

### Run with the Script

```bash
# Set your Logfire token
export LOGFIRE_TOKEN=your-logfire-token

# Run docker-logfire
./run.sh

# Or run with test containers
./run.sh --with-test
```

## Configuration

### Environment Variables

- `LOGFIRE_TOKEN` (required): Your Logfire API token
- `EXCLUDE_CONTAINERS`: Comma-separated list of container names to exclude (default: "docker-logfire")
- `INCLUDE_STOPPED`: Include logs from stopped containers (default: false)

### Docker Compose Example

```yaml
version: '3.8'

services:
  docker-logfire:
    image: docker-logfire:latest
    container_name: docker-logfire
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - LOGFIRE_TOKEN=${LOGFIRE_TOKEN}
      - EXCLUDE_CONTAINERS=docker-logfire,prometheus,grafana
    restart: unless-stopped
```

## How It Works

1. docker-logfire connects to the Docker daemon via the Docker socket
2. It discovers all running containers (excluding itself and any specified exclusions)
3. For each container, it:
   - Opens a log stream
   - Assigns the container name as the Logfire service name
   - Forwards logs to Logfire with proper metadata and timestamps
4. Continues monitoring for new containers and automatically starts streaming their logs

## Requirements

- Docker Engine API v1.40+ (Docker 19.03.0+)
- Valid Logfire account and API token
- Read-only access to Docker socket

## Security Considerations

- The container requires read-only access to the Docker socket
- Use environment variables or Docker secrets for the Logfire token
- Consider using Docker socket proxy for additional security in production

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.