FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir uv && uv sync --no-dev
ENV PYTHONPATH=/app
EXPOSE 8501
CMD ["uv", "run", "--no-sync", "streamlit", "run", "src/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
