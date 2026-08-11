FROM python:3.11-slim@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff AS python-dependencies

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libcairo2-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-lock.txt /app/requirements-lock.txt
COPY requirements-build-lock.txt /app/requirements-build-lock.txt
RUN python -m venv /opt/build-venv \
    && /opt/build-venv/bin/python -m pip install --no-cache-dir --disable-pip-version-check --no-deps -r /app/requirements-build-lock.txt \
    && mkdir -p /app/wheelhouse \
    && PATH=/opt/build-venv/bin:$PATH /opt/build-venv/bin/python -m pip wheel --no-cache-dir --disable-pip-version-check --no-deps --no-build-isolation --wheel-dir /app/wheelhouse -r /app/requirements-lock.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir --disable-pip-version-check --no-index --find-links=/app/wheelhouse --no-deps -r /app/requirements-lock.txt
COPY scripts/collect_python_licenses.py /app/scripts/collect_python_licenses.py
COPY third_party_licenses/python /app/third_party_licenses/python
RUN /opt/venv/bin/python /app/scripts/collect_python_licenses.py /app/licenses/python-runtime

FROM python:3.11-slim@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN groupadd --system diagnostic \
    && useradd --system --gid diagnostic --home-dir /nonexistent --shell /usr/sbin/nologin diagnostic

RUN apt-get update \
    && apt-get install -y --no-install-recommends libcairo2 \
    && mkdir -p /app/licenses/system-runtime \
    && for package in $(dpkg-query -W -f='${binary:Package}\n'); do \
        base=${package%%:*}; \
        copyright=/usr/share/doc/${base}/copyright; \
        if [ -f "$copyright" ]; then cp "$copyright" "/app/licenses/system-runtime/${base}.copyright"; fi; \
    done \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-dependencies /opt/venv /opt/venv
COPY --from=python-dependencies /app/licenses/python-runtime /app/licenses/python-runtime

COPY backend /app/backend
COPY school/brand.json /app/school/brand.json
COPY school/links.json /app/school/links.json
COPY school/diagnostics /app/school/diagnostics
COPY school/assets /app/school/assets
COPY LICENSE THIRD_PARTY_NOTICES.md /app/licenses/

USER diagnostic

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()"]

CMD ["python", "-m", "uvicorn", "diagnostic.api.main:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
