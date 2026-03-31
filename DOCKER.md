# Docker Setup for sw-metadata-bot

This guide helps you build and run the sw-metadata-bot using Docker containers.

## Quick Start

### Build the Docker Image

```bash
docker build -t sw-metadata-bot:latest .
```

### Run the Container

#### Show Help

```bash
docker run --rm sw-metadata-bot:latest sw-metadata-bot --help
```

#### Run Analysis with Config

```bash
docker run --rm \
  -v /path/to/config.json:/app/config.json:ro \
  -v /path/to/outputs:/app/outputs \
  sw-metadata-bot:latest \
  sw-metadata-bot run-analysis --config /app/config.json
```

#### Run with Environment Variables

```bash
docker run --rm \
  -e GITHUB_TOKEN=your_token_here \
  -v /path/to/config.json:/app/config.json:ro \
  -v /path/to/outputs:/app/outputs \
  sw-metadata-bot:latest \
  sw-metadata-bot run-analysis --config /app/config.json
```

## Docker Compose

For easier management, use Docker Compose:

### Build and Run

```bash
docker-compose build
docker-compose run --rm bot sw-metadata-bot --help
```

### Run Analysis

```bash
docker-compose run --rm bot sw-metadata-bot run-analysis --config /app/config.json
```

### Development Container

For development with all dependencies (tests, linting, docs):

```bash
docker-compose build bot-dev
docker-compose run --rm bot-dev
```

Inside the dev container:

```bash
# Run tests
pytest tests/

# Run linting
ruff check .

# Format code
ruff format .

# Build docs
cd docs && sphinx-build -W -b html . _build/html
```

## Image Details

### Multi-stage Build

The Dockerfile uses a multi-stage build process:

1. **Builder Stage**: Installs dependencies using `uv` package manager
2. **Runtime Stage**: Slim Python 3.12 image with only runtime dependencies

This approach minimizes the final image size while maintaining all functionality.

### Security Features

- **Non-root user**: Container runs as `botuser` (UID 1000) for security
- **Minimal base image**: Uses Python 3.12-slim to reduce attack surface
- **Health checks**: Built-in health check verifies CLI availability
- **Security scanning**: GitHub Actions workflow includes Trivy vulnerability scanning

### Image Size

Typical image sizes:

- Production: ~250-300 MB
- Development: ~600-700 MB

## GitHub Actions Workflow

The workflow file `.github/workflows/docker.yml` provides:

### Build Job

- Builds and pushes Docker images on main branch and tags
- Uses GitHub Container Registry (ghcr.io)
- Implements layer caching for faster builds

### Test Job

- Verifies CLI is functional
- Tests all available commands
- Validates health checks
- Inspects Docker layers

### Security Job

- Runs Trivy vulnerability scanner
- Uploads SARIF results to GitHub Security tab

### Validation Job

- Inspects image metadata
- Verifies non-root user
- Checks image size

## Configuration

### Environment Variables

Configure the bot via environment variables:

```bash
# Example with token
docker run --rm \
  -e GITHUB_TOKEN=ghp_xxxx \
  -e GITLAB_TOKEN=glpat_xxxx \
  sw-metadata-bot:latest \
  sw-metadata-bot run-analysis --config /app/config.json
```

### Volume Mounts

Standard mount points:

```bash
docker run --rm \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/outputs:/app/outputs \
  -v $(pwd)/assets:/app/assets:ro \
  sw-metadata-bot:latest
```

## Troubleshooting

### Container won't start

```bash
# Check image exists
docker images | grep sw-metadata-bot

# View container logs
docker run --rm sw-metadata-bot:latest
```

### CLI not found

```bash
# Verify installation
docker run --rm sw-metadata-bot:latest python -c "import sw_metadata_bot; print('OK')"
```

### Permission denied errors

Ensure output volume has write permissions:
```bash
chmod 755 ./outputs
```

## Advanced Usage

### Interactive Shell

```bash
docker run -it --rm \
  -v $(pwd):/workspace \
  sw-metadata-bot:latest \
  /bin/bash
```

### Run with Docker Network

```bash
docker network create bot-network
docker run --rm \
  --network bot-network \
  --name bot \
  sw-metadata-bot:latest
```

### Build specific Python version

```bash
docker build --build-arg PYTHON_VERSION=3.11 -t sw-metadata-bot:py311 .
```

## Publishing to Registry

### Push to GitHub Container Registry

```bash
# Build
docker build -t ghcr.io/yourorg/sw-metadata-bot:v1.0.0 .

# Login (use PAT token)
docker login ghcr.io

# Push
docker push ghcr.io/yourorg/sw-metadata-bot:v1.0.0
```

### Pull from Registry

```bash
docker pull ghcr.io/yourorg/sw-metadata-bot:v1.0.0
docker run --rm ghcr.io/yourorg/sw-metadata-bot:v1.0.0
```

## Development Workflow

### Local Testing

```bash
# Build
docker-compose build

# Test
docker-compose run --rm bot pytest tests/

# Lint
docker-compose run --rm bot ruff check .

# Format
docker-compose run --rm bot ruff format .
```

### Debug in Container

```bash
docker run -it --rm \
  -v $(pwd):/workspace \
  sw-metadata-bot:latest \
  /bin/bash
```

## Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Best Practices for Python Docker Images](https://docs.docker.com/language/python/build-images/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
