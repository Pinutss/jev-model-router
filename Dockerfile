FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV JEV_PROVIDER=local
ENV JEV_MODEL_HOST=0.0.0.0
ENV JEV_MODEL_PORT=8080

EXPOSE 8080
CMD ["jev-model", "serve"]
