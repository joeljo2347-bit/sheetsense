FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src src
COPY examples examples
RUN pip install --no-cache-dir ".[web]"
ENV OLLAMA_HOST=http://host.docker.internal:11434 \
    SHEETSENSE_EXAMPLES=/app/examples
EXPOSE 8000
USER nobody
CMD ["uvicorn", "sheetsense.web:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
