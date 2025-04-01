FROM python:3.11-slim

WORKDIR /app

COPY requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 確保資料目錄存在
RUN mkdir -p /app/knowledge_base
RUN mkdir -p /app/instance

# 暴露應用端口
EXPOSE 5000

# 啟動應用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]