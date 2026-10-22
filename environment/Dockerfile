# Multi-architecture OCI index pinned by digest: supports the local arm64
# Docker host as well as amd64 Harbor runners.
FROM python:3.12.5-slim-bookworm@sha256:c24c34b502635f1f7c4e99dc09a2cbd85d480b7dcfd077198c6b5af138906390

WORKDIR /app
COPY gravity_sim /app/gravity_sim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Harbor starts this as a long-lived workspace and invokes the agent inside it.
# Do not use the simulator CLI as ENTRYPOINT: without an input argument it exits
# with argparse status 2 before the agent can begin.
CMD ["sh", "-c", "while :; do sleep 3600; done"]
