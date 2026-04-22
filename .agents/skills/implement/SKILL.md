# /implement — 程式碼生成 Skill

## 目標

根據 `docs/PRD.md`、`docs/ARCHITECTURE.md` 和 `docs/MODELS.md`，生成可執行的程式碼。

## 技術規格

**我要使用 HTML 的前端與 FastAPI + SQLite 的後端。**

- **前端**：純 HTML + CSS + JavaScript（放在 `templates/` 資料夾）
- **後端**：Python FastAPI 框架
- **資料庫**：SQLite（使用 aiosqlite 進行非同步操作）
- **AI 整合**：Google Gemini API

## 前置條件

- 請先讀取 `docs/PRD.md`、`docs/ARCHITECTURE.md` 和 `docs/MODELS.md`。

## 執行步驟

1. **閱讀設計文件**：讀取所有 docs/ 下的文件，理解需求、架構與資料模型。
2. **生成後端程式碼**：建立 `app.py`，包含所有 API 路由、資料庫操作、AI 整合邏輯。
3. **生成前端頁面**：建立 `templates/index.html`，包含完整的聊天介面。
4. **生成依賴清單**：建立 `requirements.txt`，列出所有 Python 套件。
5. **生成環境範例**：建立 `.env.example`，列出需要設定的環境變數。

## 輸出檔案

### `app.py`
- FastAPI 應用程式主檔案
- 包含所有 API 端點
- 資料庫初始化與 CRUD 操作
- Gemini API 整合
- 靜態檔案與模板服務
- 檔案上傳處理

### `templates/index.html`
- 單頁式聊天介面
- 響應式設計（RWD）
- 包含以下 UI 元件：
  - 側邊欄（對話歷史列表）
  - 主聊天區域（訊息顯示）
  - 輸入區域（文字輸入 + 檔案上傳按鈕）
  - 控制按鈕（重新生成、停止回應）

### `requirements.txt`
- fastapi
- uvicorn[standard]
- python-dotenv
- google-generativeai
- aiosqlite
- python-multipart
- jinja2

### `.env.example`
```
GEMINI_API_KEY=your_gemini_api_key_here
```

## 注意事項

- 程式碼需可直接執行（`uvicorn app:app --reload`）。
- 前端使用內嵌 CSS 和 JavaScript，不需額外的建置工具。
- API 使用 RESTful 風格設計。
- 資料庫在應用啟動時自動建立資料表。
- 妥善處理錯誤情況，提供友善的錯誤訊息。
