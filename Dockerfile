# Dockerfile for polarrouteserver, intended for development use only

FROM ghcr.io/astral-sh/uv:python3.13-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=polarrouteserver.settings.development

# Install GDAL - used by Fiona
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_CONFIG=/usr/bin/gdal-config

WORKDIR /usr/src/app

COPY --chmod=775 docker-entrypoint.sh .

COPY pyproject.toml manage.py /usr/src/app/
COPY polarrouteserver /usr/src/app/polarrouteserver

ENV SETUPTOOLS_SCM_PRETEND_VERSION=99.99.99
RUN uv pip install --system -e .
RUN uv pip install --system django-debug-toolbar
