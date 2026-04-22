# /commit — 提交推送 Skill

## 目標

將目前的程式碼變更進行 Git commit 並推送到遠端倉庫。

## 重要設定

**如果需要使用者與 email，請使用預設的 Antigravity。**

不需要額外設定 git user.name 和 git user.email，直接使用 Antigravity 預設的 Git 設定即可。

## 執行步驟

1. **檢查狀態**：執行 `git status` 查看目前的變更。
2. **暫存檔案**：執行 `git add .` 將所有變更加入暫存區。
3. **提交變更**：執行 `git commit` 並撰寫有意義的 commit message。
4. **推送到遠端**：執行 `git push` 推送到遠端倉庫。

## Commit Message 格式

使用 Conventional Commits 格式：

```
<type>(<scope>): <subject>

<body>
```

### Type 類型
- `feat`：新功能
- `fix`：修正錯誤
- `docs`：文件變更
- `style`：格式變更（不影響程式碼意義）
- `refactor`：重構
- `test`：測試相關
- `chore`：其他雜項

### 範例
```
feat(chatbot): add multi-session support and chat history

- Implement session management with SQLite
- Add chat history sidebar
- Support conversation switching
```

## 注意事項

- 不要 commit 敏感資訊（如 API Key）。確認 `.env` 已加入 `.gitignore`。
- 如果有 `.gitignore` 需要更新，請在 commit 前處理。
- commit message 請使用英文撰寫，清楚描述變更內容。
- 推送前確認遠端倉庫設定正確。
