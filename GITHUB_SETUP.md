# GitHub 與 Docker 設置指南

此文檔提供將 LineBotBasic 專案上傳至 GitHub 並設置 Docker 部署的詳細步驟。

## GitHub 設置

### 1. 克隆存儲庫（如果尚未完成）

```bash
git clone https://github.com/mkhsu2002/AI_linebot.git
cd AI_linebot
```

### 2. 初始化 Git 儲存庫（如果是新專案）

```bash
git init
git add .
git commit -m "初始提交：AI_linebot V1.0"
```

### 3. 設置 GitHub 存儲庫

在 GitHub 上創建一個新的儲存庫，然後將本地存儲庫連接到 GitHub：

```bash
git remote add origin https://github.com/您的用戶名/AI_linebot.git
```

### 4. 推送到 GitHub 並加上標籤

```bash
# 推送主分支
git push -u origin main

# 創建 V1.0 標籤
git tag -a v1.0 -m "AI_linebot 初始版本"
git push origin v1.0
```

如果您使用的是 `master` 分支，使用：

```bash
git push -u origin master
git tag -a v1.0 -m "AI_linebot 初始版本"
git push origin v1.0
```

## Docker 設置

本項目已經配置好使用 Docker，以下是在各種環境中運行的指南。

### 1. 使用 Docker Compose（推薦）

使用 Docker Compose 是最簡單的方法，它會自動設置應用程序和 PostgreSQL 數據庫：

```bash
# 克隆存儲庫（如果尚未完成）
git clone https://github.com/您的用戶名/AI_linebot.git
cd AI_linebot

# 編輯環境變數
# 打開 docker-compose.yml 並更改 environment 部分的值：
# - SESSION_SECRET：更改為一個隨機的長字符串
# - OPENAI_API_KEY：設置為您的 OpenAI API 密鑰

# 構建並啟動容器
docker compose up -d

# 查看日誌
docker compose logs -f
```

應用程序將在 http://localhost:5000 上運行。

### 2. 僅使用 Docker（高級）

如果您想自己管理數據庫連接：

```bash
# 構建映像
docker build -t ai-linebot:v1.0 .

# 運行容器
docker run -d \
  -p 5000:5000 \
  -e DATABASE_URL="postgresql://用戶名:密碼@主機名:端口/數據庫名" \
  -e SESSION_SECRET="隨機秘密字符串" \
  -e OPENAI_API_KEY="您的OpenAI密鑰" \
  --name ai-linebot-app \
  ai-linebot:v1.0
```

### 3. 部署到雲平台

本應用可以部署到支持 Docker 的任何雲平台。以下是一些常見選項：

**Heroku**:
```bash
# 使用 Heroku CLI
heroku container:push web -a 您的應用名稱
heroku container:release web -a 您的應用名稱
```

**Railway/Render/Fly.io**:
這些平台支持直接從 GitHub 部署。連接您的 GitHub 帳戶，然後選擇此存儲庫。

## 保護敏感數據

確保以下敏感數據不會被提交到 GitHub：

- `.env` 文件（包含 API 密鑰）
- 任何數據庫文件（*.db）
- 日誌文件和臨時文件
- 知識庫索引文件（knowledge_base/faiss_index.idx 和 knowledge_base/embeddings.pkl）

這些文件應該列在 `.gitignore` 中，已經為您設置好了。

## 項目結構

```
.
├── app.py                  # 應用程序入口和數據庫初始化
├── main.py                 # 主應用程序啟動文件
├── models.py               # 數據庫模型定義
├── forms.py                # 表單定義
├── llm_service.py          # LLM 服務
├── rag_service.py          # 檢索增強生成服務
├── config.py               # 配置文件
├── routes/                 # 路由文件
│   ├── admin.py            # 管理面板路由
│   ├── api.py              # API 路由
│   ├── auth.py             # 認證路由
│   └── webhook.py          # LINE Bot webhook 處理
├── services/               # 服務文件
│   └── llm_service.py      # LLM 服務
├── static/                 # 靜態文件
├── templates/              # HTML 模板
├── knowledge_base/         # 知識庫目錄
├── instance/               # 實例目錄（數據庫）
├── Dockerfile              # Docker 配置
├── docker-compose.yml      # Docker Compose 配置
└── requirements-docker.txt # Docker 環境依賴
```

## 貢獻指南

1. Fork 這個存儲庫
2. 創建您的功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交您的更改 (`git commit -m '添加一些令人驚嘆的功能'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 打開一個拉取請求