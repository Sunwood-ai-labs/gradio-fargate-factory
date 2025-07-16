FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 7860

ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV PORT=7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \\
    CMD curl -f http://localhost:7860/ || exit 1

CMD ["python", "app.py"]