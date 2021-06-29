FROM debian:buster AS gosu

# grab gosu for easy step-down from root
# https://github.com/tianon/gosu/releases
# renovate: datasource=github-release depName=tianon/gosu
ENV GOSU_VERSION=1.12
# hadolint ignore=DL3008,DL4006,SC2015,SC2086,SC2155
RUN set -eux ; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates dirmngr gnupg wget; \
    dpkgArch="$(dpkg --print-architecture | awk -F- '{ print $NF }')"; \
    wget -nv -O /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$dpkgArch"; \
    wget -nv -O /usr/local/bin/gosu.asc "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$dpkgArch.asc"; \
    export GNUPGHOME="$(mktemp -d)"; \
    wget -nv -O- https://keys.openpgp.org/vks/v1/by-fingerprint/B42F6819007F00F88E364FD4036A9C25BF357DD4 | gpg --batch --import; \
    gpg --batch --verify /usr/local/bin/gosu.asc /usr/local/bin/gosu; \
    gpgconf --kill all; \
    chmod +x /usr/local/bin/gosu; \
    gosu --version; \
    gosu nobody true

FROM python:3.9.6-buster AS builder

SHELL ["/bin/bash", "-Eeux", "-o", "pipefail", "-c"]

ENV PYTHONUNBUFFERED=1 \
    POETRY_HOME=/opt/poetry

COPY poetry_install_vars.sh /usr/local/lib
# hadolint ignore=SC1091
RUN . /usr/local/lib/poetry_install_vars.sh \
    && curl -sSL -o get-poetry.py "$POETRY_URL" \
    && python get-poetry.py --yes --no-modify-path --version="$POETRY_VERSION"
ENV PATH="${POETRY_HOME}/bin:$PATH"

WORKDIR /app

COPY poetry.lock pyproject.toml ./
# hadolint ignore=SC1091
RUN python -m venv .venv \
    && . .venv/bin/activate \
    && poetry install --no-ansi --no-dev --no-interaction --no-root

COPY src ./src
# hadolint ignore=SC1091
RUN . .venv/bin/activate \
    && poetry install --no-ansi --no-dev --no-interaction

FROM python:3.9.6-slim-buster AS final

LABEL maintainer="Arnaud Rocher <arnaud.roche3@gmail.com>"
LABEL org.opencontainers.image.source https://github.com/cailloumajor/opcua-webhmi-bridge

ENV PYTHONUNBUFFERED=1

RUN useradd --user-group --system --create-home --no-log-init pythonapp \
    && mkdir /app \
    && chown pythonapp:pythonapp /app
WORKDIR /app

COPY --from=builder --chown=pythonapp:pythonapp /app /app

COPY --from=gosu /usr/local/bin/gosu /usr/local/bin/gosu
COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 8008
CMD [".venv/bin/opcua-agent"]
