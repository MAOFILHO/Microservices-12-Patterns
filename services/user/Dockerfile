# Built exclusively via `az acr build` (cloud-side) — no local Docker daemon required.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY . .
# shared/ (shop_common) is staged into ./_shared by infra/provision.py before `az acr build`.
RUN pip install --no-cache-dir --root-user-action=ignore "./_shared[flask]"

ENV RUN_MODE=azure \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 5101

# One process with threads, so the in-memory span store (pattern 6) sees every request.
CMD ["gunicorn", "--bind", "0.0.0.0:5101", "--workers", "1", "--threads", "4", "run:app"]
