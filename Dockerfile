FROM ghcr.io/astral-sh/uv:python3.13-trixie AS dev

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=polarrouteserver.settings.docker.development

# Install GDAL - used by Fiona
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_CONFIG=/usr/bin/gdal-config

WORKDIR /usr/src/app

# copy in everything for the dev stage, including the .git directory, importantly for dynamic versioning
COPY . .
COPY --chmod=775 docker-entrypoint.sh .

RUN uv pip install --system -e .
RUN uv pip install --system django-debug-toolbar debugpy

# start prod build stage, using a lighter weight base image
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS prod

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# create a non-root user (django) from which to run and serve the app
RUN useradd -m -r django && \
    mkdir /usr/src/app && \
   chown -R django /usr/src/app

# copy the python installation and packages from the dev stage
COPY --from=dev --chown=django:django /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=dev --chown=django:django /usr/local/bin/ /usr/local/bin/

WORKDIR /usr/src/app

COPY --chown=django:django --chmod=775 docker-entrypoint.sh .
COPY --chown=django:django pyproject.toml manage.py /usr/src/app/
COPY --chown=django:django polarrouteserver /usr/src/app/polarrouteserver

# set the settings module
ENV DJANGO_SETTINGS_MODULE=polarrouteserver.settings.docker.production

# install production dependencies including gunicorn
RUN uv pip install --system --group production

# set permissions on the python installed binaries
RUN chown -R django:django /usr/local/bin

# switch to the django user
USER django

# open port
EXPOSE 8000

# establish a healthcheck, using the django app's healthcheck endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1
