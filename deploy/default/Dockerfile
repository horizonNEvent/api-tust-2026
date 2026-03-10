# === IMPLANTACAO PADRAO (DEFAULT) ===
# Imagem focada em leveza, performance e economia.
# Robos que vao rodar aqui: assu, cnt, evoltz, firminopolis, tropicalia
FROM python:3.12-slim

# Define o diretorio de trabalho no container
WORKDIR /app

# Variavel de ambiente focada em producao (evita logs pyc e buffers)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala apenas pacotes essenciais de sistema (reduzindo ataques e tamanho)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala apenas os requerimentos ultraleves
COPY deploy/default/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do codigo (Classes Base, SQS Service, e codigo-fonte dos robos de Requests)
COPY . /app/

# Ponto de entrada: Sobe o processo leitor da Fila
CMD ["python", "worker/sqs_worker_service.py"]
