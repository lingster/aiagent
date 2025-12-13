# Final stage - multi-stage build
FROM ubuntu:latest
# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/appuser/.local/bin:$PATH" \
    TZ=UTC

# Add OpenContainers labels for better container metadata
LABEL org.opencontainers.image.source="https://github.com/lingster/aiagent"
LABEL org.opencontainers.image.description="AI Agent project container"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user
ARG USERNAME=appuser

# Linux Settings
ARG USER_UID=1000
ARG USER_GID=1000
# MacOS settings
#ARG USER_UID=502
#ARG USER_GID=20
# Windows Settings
ARG USER_UID=1001
ARG USER_GID=1001

RUN groupadd --gid $USER_GID $USERNAME || \
    (groupmod -g $USER_GID $USERNAME 2>/dev/null || true) && \
    useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
    mkdir -p /app/data && \
    chown -R $USER_UID:$USER_GID /app

# Install runtime dependencies (including ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    git \
    vim \
    less \
    build-essential \
    patch \
    ca-certificates \
    apt-transport-https \
    gnupg \
    tzdata \
    libmagic1 libmagic-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install git-lfs
RUN curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | bash && \
    apt-get update && \
    apt-get install -y git-lfs && \
    # Clean up to reduce image size
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# User switch
USER $USERNAME

# Install NVM
WORKDIR /home/$USERNAME/.nvm
WORKDIR /home/$USERNAME
ENV HOME=/home/$USERNAME
ENV NVM_DIR=/home/$USERNAME/.nvm
ENV NODE_VERSION=20.18.3
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && \
    . $NVM_DIR/nvm.sh && \
    nvm install $NODE_VERSION && \
    nvm alias default $NODE_VERSION && \
    nvm use default && \ 
    npm install -g tree-sitter-cli

# Add NVM to PATH
ENV PATH=$NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH
ENV TMPDIR=/tmp

# Verify installation
RUN node --version && \
    npm --version

# Setup shell for proper NVM usage
RUN echo 'export NVM_DIR="$HOME/.nvm"' >> ~/.bashrc && \
    echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.bashrc && \
    echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> ~/.bashrc


# Initialize git-lfs
RUN git lfs install

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy application files
COPY --chown=$USER_UID:$USER_GID pyproject.toml remote_server.py config.py /app/
COPY --chown=$USER_UID:$USER_GID remote_server_lib /app/remote_server_lib/

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN uv sync

# Expose port
EXPOSE 8000

# Working directory for data
WORKDIR /data

# setup git commits
RUN git config --global user.email "aiagent@techarge.co.uk"
RUN git config --global user.name "aiagent"

# Run the application
CMD ["uv", "run", "uvicorn", "remote_server:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app"]

