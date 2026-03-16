# === IMPLANTACAO BROWSER (TIER B) ===
# Imagem focada em automacao de navegadores (Selenium/Playwright).
FROM mcr.microsoft.com/playwright:v1.45.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala Python e dependencias de sistema adicionais caso necessario
RUN apt-get update && apt-get install -y python3-pip && rm -rf /var/lib/apt/lists/*

# Copia e instala requerimentos (Selenium, Playwright, etc)
COPY deploy/browser/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Instala os binarios dos browsers do Playwright
RUN playwright install chromium

COPY . /app/

CMD ["python3", "worker/sqs_worker_service.py"]
