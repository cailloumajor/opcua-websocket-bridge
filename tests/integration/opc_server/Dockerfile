FROM python:3.9-slim

ENV PYTHONUNBUFFERED 1

SHELL ["/bin/bash", "-Eeux", "-o", "pipefail", "-c"]

RUN useradd --user-group --system --create-home --no-log-init pythonapp \
    && mkdir /app \
    && chown pythonapp:pythonapp /app
USER pythonapp
WORKDIR /app

COPY opc_server.py \
     requirements.txt \
     test-server-cert.der \
     test-server-key.pem \
     ./

# hadolint ignore=SC1091
RUN python -m venv .venv \
    && . .venv/bin/activate \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 4840
EXPOSE 8080

CMD [".venv/bin/python", "opc_server.py", "8080"]
