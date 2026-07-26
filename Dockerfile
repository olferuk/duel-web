# Дуэль за Средиземье — torch-free веб (ONNX-инференс, влезает в бесплатные тиры)
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir numpy fastapi uvicorn pydantic onnxruntime
COPY src /app/src
COPY analysis/lab/models/w3.onnx /app/analysis/lab/models/w3.onnx
ENV PYTHONPATH=/app/src DUEL_HOST=0.0.0.0 DUEL_PUBLIC=1 DUEL_ONNX=1 PORT=10000
RUN useradd -m duel
USER duel
EXPOSE 10000
CMD ["python", "-m", "duel.web.server"]
