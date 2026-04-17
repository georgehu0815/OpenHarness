FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ripgrep \
        curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
        && rm -rf /var/lib/apt/lists/*
    # && apt-get install -y --no-install-recommends nodejs \
    # && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -e . && pip cache purge

# Bundle host skills outside the volume mount so they survive the /data/ohmo overlay.
# The entrypoint copies these into $WORKSPACE/skills/ on every startup.
COPY skills/ /app/bundled-skills/

# Install tpm CLI (staged into tpm/ before build)
COPY tpm/ /opt/tpm/
RUN pip install --no-cache-dir -r /opt/tpm/requirements.txt \
    && printf '#!/bin/sh\nexec python3 /opt/tpm/tpm_cli.py "$@"\n' > /usr/local/bin/tpm \
    && chmod +x /usr/local/bin/tpm

# Workspace volume — gateway config, sessions, logs, memory live here
ENV OHMO_WORKSPACE=/data/ohmo

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

VOLUME ["/data/ohmo"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["ohmo", "gateway", "run", "--cwd", "/app", "--workspace", "/data/ohmo"]
