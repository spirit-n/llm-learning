FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home learner \
    && mkdir /app/data \
    && chown learner:learner /app/data
USER learner
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"
CMD ["python", "-m", "uvicorn", "deploy_lab.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
