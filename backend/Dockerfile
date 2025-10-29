FROM python:3.9-slim

WORKDIR /app

# Instala o pip e as dependências
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copia o código da aplicação
COPY . .

# Expõe a porta e define o comando de execução
EXPOSE 5003
CMD ["flask", "run", "--host=0.0.0.0", "--port=5003"]
