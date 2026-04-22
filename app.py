"""
AI Chatbot - FastAPI + SQLite Backend
"""
import os
import uuid
import json
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import aiosqlite
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import google.generativeai as genai

load_dotenv()

# --- Configuration ---
DB_PATH = "chatbot.db"
UPLOAD_DIR = "uploads"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Gemini Setup ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Tool definitions for Gemini function calling
weather_tool = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name="get_weather",
            description="Get the current weather for a given city. Use this when the user asks about weather.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "city": genai.protos.Schema(type=genai.protos.Type.STRING, description="The city name"),
                },
                required=["city"],
            ),
        ),
        genai.protos.FunctionDeclaration(
            name="calculate",
            description="Evaluate a mathematical expression. Use this for math calculations.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "expression": genai.protos.Schema(type=genai.protos.Type.STRING, description="The math expression to evaluate, e.g. '2+2' or 'sqrt(16)'"),
                },
                required=["expression"],
            ),
        ),
    ]
)

SYSTEM_PROMPT = """你是一個友善且有幫助的 AI 助手。請用繁體中文回覆。
你具備以下工具能力：
1. 天氣查詢：可以查詢城市的即時天氣
2. 數學計算：可以計算數學表達式

如果使用者告訴你他的偏好或個人資訊，請在回覆中自然地記住並使用這些資訊。
"""


# --- Database ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '新對話',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                file_path TEXT,
                file_type TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp);
        """)
        await db.commit()


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# --- Helper Functions ---
def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def get_memories_text():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM memories")
        rows = await cursor.fetchall()
        if not rows:
            return ""
        lines = [f"- {r['key']}: {r['value']}" for r in rows]
        return "以下是你記得的使用者資訊：\n" + "\n".join(lines)
    finally:
        await db.close()


async def extract_and_save_memories(content: str):
    """Use Gemini to extract memorable info from AI response."""
    if not GEMINI_API_KEY:
        return
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""分析以下 AI 回覆，提取使用者偏好或個人資訊。
如果有值得記憶的資訊，回傳 JSON 陣列，每個元素格式為 {{"key": "英文key", "value": "中文描述"}}。
如果沒有，回傳空陣列 []。
只回傳 JSON，不要其他文字。

AI 回覆：
{content}"""
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        items = json.loads(text)
        if not items:
            return
        db = await get_db()
        try:
            for item in items:
                k, v = item.get("key", ""), item.get("value", "")
                if k and v:
                    t = now_iso()
                    await db.execute(
                        """INSERT INTO memories (key, value, created_at, updated_at)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?""",
                        (k, v, t, t, v, t),
                    )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass


async def call_tool(name: str, args: dict) -> str:
    """Execute a tool function and return result as string."""
    if name == "get_weather":
        city = args.get("city", "unknown")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://wttr.in/{city}?format=j1", timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    current = data.get("current_condition", [{}])[0]
                    temp = current.get("temp_C", "N/A")
                    desc = current.get("lang_zh", [{}])
                    desc_text = desc[0].get("value", current.get("weatherDesc", [{}])[0].get("value", "")) if desc else current.get("weatherDesc", [{}])[0].get("value", "")
                    humidity = current.get("humidity", "N/A")
                    wind = current.get("windspeedKmph", "N/A")
                    return json.dumps({"city": city, "temperature_c": temp, "description": desc_text, "humidity": f"{humidity}%", "wind_speed": f"{wind} km/h"}, ensure_ascii=False)
        except Exception:
            pass
        return json.dumps({"city": city, "temperature_c": "22", "description": "晴", "humidity": "60%", "wind_speed": "10 km/h", "note": "模擬資料"}, ensure_ascii=False)

    elif name == "calculate":
        expr = args.get("expression", "0")
        try:
            import math
            allowed = {"__builtins__": {}, "math": math, "sqrt": math.sqrt, "pi": math.pi, "e": math.e, "abs": abs, "round": round, "pow": pow}
            result = eval(expr, allowed)
            return json.dumps({"expression": expr, "result": str(result)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"expression": expr, "error": str(e)}, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {name}"})


# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("templates/index.html")


# Sessions
@app.get("/api/sessions")
async def list_sessions():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


@app.post("/api/sessions")
async def create_session():
    db = await get_db()
    try:
        sid = str(uuid.uuid4())
        t = now_iso()
        await db.execute("INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)", (sid, "新對話", t, t))
        await db.commit()
        return {"id": sid, "title": "新對話", "created_at": t, "updated_at": t}
    finally:
        await db.close()


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    db = await get_db()
    try:
        await db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@app.put("/api/sessions/{session_id}")
async def update_session(session_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "")
    db = await get_db()
    try:
        await db.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (title, now_iso(), session_id))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# Messages
@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY timestamp", (session_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# Upload
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    allowed = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"不支援的檔案類型: {file.content_type}")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "檔案大小不可超過 10MB")
    ext = os.path.splitext(file.filename or "file")[1]
    fname = f"{uuid.uuid4()}{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(content)
    return {"file_path": f"/uploads/{fname}", "file_type": file.content_type, "file_name": file.filename}


# Chat (SSE streaming)
@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    content = body.get("content", "")
    file_path = body.get("file_path")
    file_type = body.get("file_type")

    if not session_id or not content.strip():
        raise HTTPException(400, "session_id and content are required")

    db = await get_db()
    try:
        # Save user message
        t = now_iso()
        await db.execute(
            "INSERT INTO messages (session_id, role, content, timestamp, file_path, file_type) VALUES (?,?,?,?,?,?)",
            (session_id, "user", content, t, file_path, file_type),
        )
        await db.commit()

        # Load history
        cursor = await db.execute("SELECT role, content, file_path, file_type FROM messages WHERE session_id=? ORDER BY timestamp", (session_id,))
        rows = await cursor.fetchall()
        history = [dict(r) for r in rows]

        # Update session title from first user message
        user_msgs = [h for h in history if h["role"] == "user"]
        if len(user_msgs) == 1:
            title = content[:30] + ("..." if len(content) > 30 else "")
            await db.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (title, t, session_id))
            await db.commit()
    finally:
        await db.close()

    # Build Gemini messages
    memories_text = await get_memories_text()
    system_text = SYSTEM_PROMPT
    if memories_text:
        system_text += "\n\n" + memories_text

    gemini_messages = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        parts = []
        # If has image, include it
        if h.get("file_path") and h.get("file_type", "").startswith("image/"):
            try:
                local_path = h["file_path"].lstrip("/")
                with open(local_path, "rb") as f:
                    img_data = f.read()
                parts.append(genai.protos.Part(inline_data=genai.protos.Blob(mime_type=h["file_type"], data=img_data)))
            except Exception:
                pass
        parts.append(genai.protos.Part(text=h["content"]))
        gemini_messages.append({"role": role, "parts": parts})

    async def generate():
        if not GEMINI_API_KEY:
            error_msg = "⚠️ 請先設定 GEMINI_API_KEY 環境變數。請在 .env 檔案中填入你的 API Key。"
            yield f"data: {json.dumps({'text': error_msg})}\n\n"
            yield f"data: {json.dumps({'done': True, 'full_text': error_msg})}\n\n"
            db2 = await get_db()
            try:
                await db2.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)", (session_id, "assistant", error_msg, now_iso()))
                await db2.commit()
            finally:
                await db2.close()
            return

        try:
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=system_text,
                tools=[weather_tool],
            )
            chat_obj = model.start_chat(history=gemini_messages[:-1])
            response = chat_obj.send_message(gemini_messages[-1]["parts"], stream=True)

            full_text = ""
            for chunk in response:
                # Handle function calls
                if chunk.candidates and chunk.candidates[0].content.parts:
                    for part in chunk.candidates[0].content.parts:
                        if hasattr(part, "function_call") and part.function_call.name:
                            fc = part.function_call
                            tool_name = fc.name
                            tool_args = dict(fc.args) if fc.args else {}
                            yield f"data: {json.dumps({'text': f'🔧 使用工具: {tool_name}...'})}\n\n"
                            await asyncio.sleep(0)

                            result = await call_tool(tool_name, tool_args)
                            tool_response = chat_obj.send_message(
                                genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=tool_name,
                                        response={"result": json.loads(result)},
                                    )
                                ),
                                stream=True,
                            )
                            for tc in tool_response:
                                if tc.text:
                                    full_text += tc.text
                                    yield f"data: {json.dumps({'text': tc.text})}\n\n"
                                    await asyncio.sleep(0)
                            continue
                        if hasattr(part, "text") and part.text:
                            full_text += part.text
                            yield f"data: {json.dumps({'text': part.text})}\n\n"
                            await asyncio.sleep(0)

            yield f"data: {json.dumps({'done': True, 'full_text': full_text})}\n\n"

            # Save assistant message
            db2 = await get_db()
            try:
                await db2.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)", (session_id, "assistant", full_text, now_iso()))
                await db2.commit()
            finally:
                await db2.close()

            # Extract memories in background
            asyncio.create_task(extract_and_save_memories(content + "\n---\n" + full_text))

        except Exception as e:
            err = f"❌ 錯誤：{str(e)}"
            yield f"data: {json.dumps({'text': err, 'done': True, 'full_text': err})}\n\n"
            db2 = await get_db()
            try:
                await db2.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)", (session_id, "assistant", err, now_iso()))
                await db2.commit()
            finally:
                await db2.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


# Regenerate
@app.post("/api/chat/regenerate")
async def regenerate(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    if not session_id:
        raise HTTPException(400, "session_id is required")

    db = await get_db()
    try:
        # Delete last assistant message
        cursor = await db.execute(
            "SELECT id FROM messages WHERE session_id=? AND role='assistant' ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row:
            await db.execute("DELETE FROM messages WHERE id=?", (row["id"],))
            await db.commit()

        # Get last user message content (keep it in DB)
        cursor = await db.execute(
            "SELECT content, file_path, file_type FROM messages WHERE session_id=? AND role='user' ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        )
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(400, "No user message to regenerate from")

        user_content = user_row["content"]
        user_file_path = user_row["file_path"]
        user_file_type = user_row["file_type"]

        # Load history (user message is still there)
        cursor = await db.execute("SELECT role, content, file_path, file_type FROM messages WHERE session_id=? ORDER BY timestamp", (session_id,))
        rows = await cursor.fetchall()
        history = [dict(r) for r in rows]
    finally:
        await db.close()

    # Build Gemini messages
    memories_text = await get_memories_text()
    system_text = SYSTEM_PROMPT
    if memories_text:
        system_text += "\n\n" + memories_text

    gemini_messages = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        parts = []
        if h.get("file_path") and h.get("file_type", "").startswith("image/"):
            try:
                local_path = h["file_path"].lstrip("/")
                with open(local_path, "rb") as f:
                    img_data = f.read()
                parts.append(genai.protos.Part(inline_data=genai.protos.Blob(mime_type=h["file_type"], data=img_data)))
            except Exception:
                pass
        parts.append(genai.protos.Part(text=h["content"]))
        gemini_messages.append({"role": role, "parts": parts})

    async def gen_regen():
        if not GEMINI_API_KEY:
            error_msg = "⚠️ 請先設定 GEMINI_API_KEY"
            yield f"data: {json.dumps({'text': error_msg, 'done': True, 'full_text': error_msg})}\n\n"
            return
        try:
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_text, tools=[weather_tool])
            chat_obj = model.start_chat(history=gemini_messages[:-1])
            response = chat_obj.send_message(gemini_messages[-1]["parts"], stream=True)
            full_text = ""
            for chunk in response:
                if chunk.candidates and chunk.candidates[0].content.parts:
                    for part in chunk.candidates[0].content.parts:
                        if hasattr(part, "function_call") and part.function_call.name:
                            fc = part.function_call
                            yield f"data: {json.dumps({'text': f'🔧 使用工具: {fc.name}...'})}\n\n"
                            await asyncio.sleep(0)
                            result = await call_tool(fc.name, dict(fc.args) if fc.args else {})
                            tr = chat_obj.send_message(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=fc.name, response={"result": json.loads(result)})), stream=True)
                            for tc in tr:
                                if tc.text:
                                    full_text += tc.text
                                    yield f"data: {json.dumps({'text': tc.text})}\n\n"
                                    await asyncio.sleep(0)
                            continue
                        if hasattr(part, "text") and part.text:
                            full_text += part.text
                            yield f"data: {json.dumps({'text': part.text})}\n\n"
                            await asyncio.sleep(0)
            yield f"data: {json.dumps({'done': True, 'full_text': full_text})}\n\n"
            db2 = await get_db()
            try:
                await db2.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)", (session_id, "assistant", full_text, now_iso()))
                await db2.commit()
            finally:
                await db2.close()
        except Exception as e:
            err = f"❌ 錯誤：{str(e)}"
            yield f"data: {json.dumps({'text': err, 'done': True, 'full_text': err})}\n\n"

    return StreamingResponse(gen_regen(), media_type="text/event-stream")


# Memories
@app.get("/api/memories")
async def list_memories():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM memories ORDER BY updated_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@app.delete("/api/memories")
async def clear_memories():
    db = await get_db()
    try:
        await db.execute("DELETE FROM memories")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
