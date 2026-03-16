# === DOCKERFILE CONSOLIDADO TUST 2026 ===
# Imagem unica "All-in-One" para simplificar Pipeline e Infraestrutura.

FROM mcr.microsoft.com/playwright:v1.45.0-jammy

WORKDIR /app

# Variaveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Instala dependencias de sistema (Geral + Browser + OCR + PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    wget \
    wkhtmltopdf \
    libgl1-mesa-glx \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 2. Copia e instala requerimentos Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 3. Instala binarios do Playwright (Chromium)
RUN playwright install chromium

# 4. Pre-download de modelos OCR para evitar atraso na primeira execucao (Cold Start)
RUN python3 -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='pt', use_gpu=False)"

# 5. Copia o restante do codigo
COPY . .

# Comando default: Inicia o Worker (que agora ouve uma fila única)
CMD ["python3", "worker/sqs_worker_service.py"]
