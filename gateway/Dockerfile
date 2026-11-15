# Built exclusively via `az acr build` (cloud-side) — no local Docker daemon required.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY . .
# shared/ (shop_common) is staged into ./_shared by infra/provision.py before `az acr build`.
RUN pip install --no-cache-dir --root-user-action=ignore "./_shared[fastapi]"

ENV RUN_MODE=azure \
    PYTHONUNBUFFERED=1

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
