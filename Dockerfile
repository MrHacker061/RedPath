# syntax=docker/dockerfile:1
FROM python:3.13-slim

# AppPaths reads LOCALAPPDATA on every platform, so data lands in /data/RedPath.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LOCALAPPDATA=/data

WORKDIR /app

# Dependencies come from pyproject.toml in their own layer so source edits skip reinstalling them.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# AppPaths resolves frontend/ next to the packages, so keep the source tree layout.
COPY redpath ./redpath
COPY redpath_ai ./redpath_ai
COPY redpath_kali ./redpath_kali
COPY redpath_setup ./redpath_setup
COPY frontend ./frontend

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin redpath \
    && mkdir /data && chown redpath:redpath /data
USER redpath

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % os.environ.get('REDPATH_PORT', '8000'), timeout=3)"

CMD ["python", "-m", "redpath.container"]
