# === IMPLANTACAO OCR HEAVY ===
# Imagem focada em Visao Computacional. Robusta e maior tamanho.
# Robos que vao rodar aqui: light (e os futuros que usarem OpenCV/PaddleOCR)
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala bibliotecas de sistema criticas para processamento de Imagem (OpenCV) e geracao e PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    wkhtmltopdf \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Instala requerimentos grandes (PaddleOCR, OpenCV, PDFKit)
COPY deploy/ocr_heavy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-baixa os modelos do PaddleOCR (English Only para Captchas) no container 
# para ele nao perder tempo de boot quando o KEDA escalar a fila do nada
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(lang='en')"

COPY . /app/

CMD ["python", "worker/sqs_worker_service.py"]
