# Pattern 9: one image per service, built only in the cloud (az acr build) or in GitHub Actions,
# always for linux/amd64 (Azure Container Apps). Never built on the owner's arm64 Mac.
#
# Stage 1 installs dependencies into a virtualenv. Stage 2 copies only that virtualenv and the
# source into a clean image and runs as an unprivileged user, so no compiler cache, pip cache or
# root process ends up in production.

FROM python:3.12-slim AS build
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# shared/ (shop_common) is staged into ./_shared before the build (infra/provision.py, CI).
COPY _shared ./_shared
RUN pip install --no-cache-dir "./_shared[flask]"

FROM python:3.12-slim
ARG GIT_SHA=unknown
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUN_MODE=azure \
    FLASK_ENV=production \
    GIT_SHA=$GIT_SHA
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=10001:10001 . .
RUN rm -rf _shared && mkdir -p instance && chown 10001:10001 instance
USER 10001
EXPOSE 5101

# One process with threads, so the in-memory span store (pattern 6) sees every request.
CMD ["gunicorn", "--bind", "0.0.0.0:5101", "--workers", "1", "--threads", "4", "run:app"]
