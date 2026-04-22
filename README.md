# 作業：設計 Skill + 打造 AI 聊天機器人

> **繳交方式**：將你的 GitHub repo 網址貼到作業繳交區
> **作業性質**：個人作業

---

## 作業目標

使用 Antigravity Skill 引導 AI，完成一個具備前後端的 AI 聊天機器人。
重點不只是「讓程式跑起來」，而是透過設計 Skill，學會用結構化的方式與 AI 協作開發。

---

## 繳交項目

你的 GitHub repo 需要包含以下內容：

### 1. Skill 設計（`.agents/skills/`）

為以下五個開發階段＋提交方式各設計一個 SKILL.md：

| 資料夾名稱        | 對應指令          | 說明                                                                           |
| ----------------- | ----------------- | ------------------------------------------------------------------------------ |
| `prd/`          | `/prd`          | 產出 `docs/PRD.md`                                                           |
| `architecture/` | `/architecture` | 產出 `docs/ARCHITECTURE.md`                                                  |
| `models/`       | `/models`       | 產出 `docs/MODELS.md`                                                        |
| `implement/`    | `/implement`    | 產出程式碼（**需指定**：HTML 前端 + FastAPI + SQLite 後端）              |
| `test/`         | `/test`         | 產出手動測試清單                                                               |
| `commit/`       | `/commit`       | 自動 commit + push（**需指定**：使用者與 email 使用 Antigravity 預設值） |

### 2. 開發文件（`docs/`）

用你設計的 Skill 產出的文件，需包含：

- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/MODELS.md`

### 3. 程式碼

一個可執行的 AI 聊天機器人，需支援以下功能：

| 功能           | 說明                                       | 是否完成 |
| -------------- | ------------------------------------------ | -------- |
| 對話狀態管理   | 支援多聊天室（session），維持上下文        | O        |
| 訊息系統       | 訊息結構包含 role、content、timestamp      | O        |
| 對話歷史管理   | 可顯示並切換過去的對話紀錄                 | O        |
| 上傳圖片或文件 | 支援使用者上傳檔案作為對話內容             | O        |
| 回答控制       | 提供重新生成（regenerate）或中止回應的功能 | O        |
| 記憶機制       | 儲存使用者偏好，實現跨對話持續性           | O        |
| 工具整合       | 串接外部 API，使聊天機器人具備實際操作能力 | O        |

---

### 各功能對應程式碼說明

#### 1. 對話狀態管理

透過 SQLite `sessions` 資料表管理多個獨立聊天室，每個 session 有唯一 UUID。

**後端 (`app.py`)**：
- `create_session()` — `POST /api/sessions`：建立新聊天室，產生 UUID 並寫入資料庫
- `list_sessions()` — `GET /api/sessions`：取得所有聊天室，按更新時間倒序排列
- `delete_session()` — `DELETE /api/sessions/{id}`：刪除聊天室（CASCADE 同步刪除訊息）
- `switch_session()` — 前端切換聊天室時，呼叫 `GET /api/sessions/{id}/messages` 載入該 session 的歷史

**前端 (`templates/index.html`)**：
- `newChat()` — 建立新 session 並切換
- `switchSession(id, title)` — 切換到指定 session，載入對應訊息
- `deleteSession(id)` — 刪除指定 session

---

#### 2. 訊息系統

每則訊息以 `{role, content, timestamp}` 結構儲存在 `messages` 資料表。

**後端 (`app.py`)**：
- `chat()` — `POST /api/chat`：接收使用者訊息，儲存至資料庫（含 role='user'、content、ISO 8601 timestamp），載入完整歷史送給 Gemini API，以 SSE 串流回傳 AI 回覆
- `get_messages()` — `GET /api/sessions/{id}/messages`：查詢指定 session 的所有訊息

**資料表結構**：
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    file_path TEXT,
    file_type TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

---

#### 3. 對話歷史管理

側邊欄顯示所有歷史對話，可點擊切換、刪除。

**後端 (`app.py`)**：
- `list_sessions()` — 回傳所有 session（含標題、更新時間）
- `update_session()` — `PUT /api/sessions/{id}`：更新聊天室標題
- 首次訊息時自動以使用者輸入的前 30 字作為聊天室標題

**前端 (`templates/index.html`)**：
- `loadSessions()` — 從 API 載入所有 session 並渲染到側邊欄
- 每個 session item 顯示標題 + 刪除按鈕（hover 時顯示）
- `switchSession()` — 點擊切換，載入該 session 的所有訊息

---

#### 4. 上傳圖片或文件

支援上傳圖片（PNG/JPG/GIF/WebP）、PDF、純文字檔，大小限制 10MB。

**後端 (`app.py`)**：
- `upload_file()` — `POST /api/upload`：驗證檔案類型與大小，儲存至 `uploads/` 目錄，回傳檔案路徑
- `chat()` — 送出訊息時若有附件，將圖片以 `inline_data` 方式送給 Gemini，讓 AI 可以「看到」圖片內容

**前端 (`templates/index.html`)**：
- `handleFile(event)` — 處理檔案選擇，上傳到伺服器，顯示預覽
- `clearFile()` — 清除已選擇的檔案
- 圖片以縮圖預覽，非圖片檔顯示檔名

---

#### 5. 回答控制

提供「重新生成」和「停止回應」兩個控制功能。

**後端 (`app.py`)**：
- `regenerate()` — `POST /api/chat/regenerate`：刪除最後一條 AI 回覆，重新用相同的歷史向 Gemini 發送請求，以 SSE 串流回傳新的回覆

**前端 (`templates/index.html`)**：
- `regenerate()` — 移除畫面上最後一條 AI 訊息，呼叫 regenerate API 重新生成
- `stopGeneration()` — 使用 `AbortController` 中斷 fetch 請求，停止接收串流回應
- 送出訊息時隱藏送出按鈕、顯示停止按鈕；生成完畢後恢復

---

#### 6. 記憶機制

透過 Gemini 自動提取使用者偏好，儲存於 `memories` 資料表，跨所有聊天室共用。

**後端 (`app.py`)**：
- `extract_and_save_memories(content)` — 每次 AI 回覆後，背景呼叫 Gemini 分析對話內容，提取使用者偏好（如姓名、語言偏好等），以 key-value 形式儲存
- `get_memories_text()` — 每次發送訊息時，載入所有記憶並注入到系統提示詞中
- `list_memories()` — `GET /api/memories`：查詢所有記憶
- `delete_memory()` — `DELETE /api/memories/{id}`：刪除指定記憶
- `clear_memories()` — `DELETE /api/memories`：清除所有記憶

**前端 (`templates/index.html`)**：
- `openMemories()` — 開啟記憶管理 Modal，顯示所有已儲存的記憶
- `deleteMemory(id)` — 刪除單筆記憶
- `clearAllMemories()` — 清除全部記憶

---

#### 7. 工具整合（Tool Use）

透過 Gemini Function Calling 機制，讓 AI 可以呼叫外部工具。

**後端 (`app.py`)**：
- `weather_tool` — 使用 `genai.protos.Tool` 定義工具（天氣查詢 `get_weather`、數學計算 `calculate`）
- `call_tool(name, args)` — 執行工具函式：
  - `get_weather(city)` — 呼叫 [wttr.in](https://wttr.in) API 取得即時天氣（溫度、濕度、風速、天氣描述）
  - `calculate(expression)` — 安全地計算數學表達式（使用 `math` 模組）
- 在 `chat()` 和 `regenerate()` 中，偵測 Gemini 回傳的 `function_call`，呼叫對應工具後將結果送回 Gemini 組合最終回覆

**使用範例**：
- 使用者輸入「台北現在天氣如何？」→ AI 呼叫 `get_weather("台北")` → 回覆即時天氣
- 使用者輸入「計算 sqrt(144) + 25」→ AI 呼叫 `calculate("sqrt(144) + 25")` → 回覆 37.0

---

### 4. 系統截圖（`screenshots/`）

在 `screenshots/` 資料夾放入以下截圖：

- `chat.png`：聊天機器人主畫面，**需包含至少一輪完整的對話**
- `history.png`：對話歷史或多 session 切換的畫面

### 5. 心得報告（本 README.md 下方）

在本 README 的**心得報告**區填寫。

---

## 專案結構範例

```
your-repo/
├── .agents/
│   └── skills/
│       ├── prd/SKILL.md
│       ├── architecture/SKILL.md
│       ├── models/SKILL.md
│       ├── implement/SKILL.md
│       ├── test/SKILL.md
│       └── commit/SKILL.md
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── MODELS.md
├── templates/
│   └── index.html
├── screenshots/
│   ├── chat.png
│   ├── history.png
│   └── skill.png
├── app.py
├── requirements.txt
├── .env.example
└── README.md          ← 本檔案（含心得報告）
```

---

## 啟動方式

```bash
# 1. 建立虛擬環境
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. 安裝套件
pip install -r requirements.txt

# 3. 設定環境變數
cp .env.example .env
# 編輯 .env，填入 GEMINI_API_KEY

# 4. 啟動伺服器
uvicorn app:app --reload
# 開啟瀏覽器：http://localhost:8000
```

---

## 心得報告

**姓名**：
**學號**：

### 問題與反思

**Q1. 你設計的哪一個 Skill 效果最好？為什麼？哪一個效果最差？你認為原因是什麼？**

> **效果最好：`/implement`（程式碼生成）**
>
> 因為這個 Skill 的指示最具體——明確指定了技術棧（HTML 前端 + FastAPI + SQLite）、輸出檔案清單（app.py、templates/index.html、requirements.txt、.env.example），以及每個檔案應包含的內容。具體的約束條件讓 AI 幾乎不需要猜測，能直接產出可執行的程式碼。這說明 Skill 越具體、越有結構，AI 的產出品質就越高。
>
> **效果最差：`/commit`（提交推送）**
>
> 因為 commit 本身是一個操作型任務，不像文件生成那樣有明確的輸出格式可以規範。Skill 主要只能描述「用什麼格式寫 commit message」和「不要 commit 敏感資訊」，但實際執行時 AI 還是需要根據當下的 git 狀態做判斷，Skill 能引導的範圍有限。此外，git 操作涉及環境設定（如 user.name、email），這些是 Skill 較難完全控制的外部因素。

---

**Q2. 在用 AI 產生程式碼的過程中，你遇到什麼問題是 AI 沒辦法自己解決、需要你介入處理的？**

> 1. **API Key 管理**：AI 無法自動取得有效的 Gemini API Key，需要我手動到 Google AI Studio 申請並填入 `.env` 檔案。當 API Key 過期或免費額度用完時，AI 只能顯示錯誤訊息，無法自行修復。
>
> 2. **套件版本相容性**：AI 產生的程式碼使用了 `Jinja2Templates` 的舊版 API（`TemplateResponse("index.html", {"request": request})`），但實際安裝的 Starlette 新版已改變了呼叫方式，導致 `TypeError: unhashable type: 'dict'` 錯誤。AI 需要多次除錯才找到正確的寫法，最終改用 `FileResponse` 繞過問題。
>
> 3. **Gemini 模型額度限制**：`gemini-2.0-flash` 的免費額度用完後，需要我手動將模型名稱改為 `gemini-2.5-flash`。AI 雖然能建議解決方案，但無法預知哪個模型目前有可用額度。
>
> 4. **`google.generativeai` 套件已棄用**：AI 使用的 `google.generativeai` 套件已被標記為 deprecated，官方建議改用 `google.genai`。這是 AI 訓練資料的時間差問題，需要開發者自行注意並決定是否遷移。
