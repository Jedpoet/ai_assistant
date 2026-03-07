import os
import json
from datetime import date, timedelta
from google import genai
from google.genai import types
from db.database import get_fixed_schedules, get_member
from calendar.gcal import get_events_for_week
from dotenv import load_dotenv

load_dotenv()

client = genai.Client()

DAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def _build_context(member_row, today: date) -> str:
    """組出注入給 Claude 的當前狀態 context"""
    week_start = today - timedelta(days=today.weekday())

    # 固定行程
    fixed = get_fixed_schedules(member_row["id"])
    fixed_text = (
        "\n".join(
            f"  {DAY_NAMES[s['day_of_week']]} {s['start_time']}–{s['end_time']} {s['title']}"
            for s in fixed
        )
        or "  （無）"
    )

    # Google Calendar 動態事件
    dynamic_text = "  （無）"
    if member_row["calendar_id"]:
        events = get_events_for_week(member_row["calendar_id"], week_start)
        if events:
            dynamic_text = "\n".join(
                f"  {e['start']} – {e['end']}  {e['title']}" for e in events
            )

    preferences = member_row["preferences"] or "（無特別偏好）"

    return f"""今天日期：{today.strftime("%Y-%m-%d")} ({DAY_NAMES[today.weekday()]})
本週開始：{week_start.strftime("%Y-%m-%d")}

固定行程（每週重複）：
{fixed_text}

本週動態事件：
{dynamic_text}

使用者偏好：{preferences}"""


SYSTEM_PROMPT = """你是一個家庭行程助理，負責解析使用者的自然語言並決定要執行的動作。

## Intent 說明

- **add_event**：一次性事件（例如：「下週四看牙醫」、「明天下午開會兩小時」）
- **add_fixed**：每週固定重複的行程（例如：「我每週一到五早上八點上班到五點」、「週三晚上七點鋼琴課一小時」）
- **ask**：使用者說的是行程相關的事，但缺少必要資訊（時間、日期或時長），需要追問
- **ignore**：與行程無關的一般聊天，不需要處理

## 規則

1. 只輸出 JSON，不要加任何說明文字或 markdown。
2. 避免與固定行程或已有事件衝突；若有衝突，改用 ask 告知使用者。
3. 時間使用 ISO 8601（例如 2024-03-15T14:00:00）。
4. 固定行程的 days 為陣列，0=週一…6=週日。

## 回傳格式

```
{
  "intent": "add_event" | "add_fixed" | "ask" | "ignore",

  // intent=add_event 時：
  "event": {
    "title": "事件名稱",
    "start": "ISO8601",
    "end": "ISO8601",
    "note": "備註（可空）"
  },

  // intent=add_fixed 時：
  "fixed": {
    "title": "行程名稱",
    "days": [0, 1, 2, 3, 4],
    "start_time": "HH:MM",
    "end_time": "HH:MM"
  },

  // intent=ask 時：
  "question": "用繁體中文問使用者缺少的資訊"
}
```
"""


def parse_message(
    discord_id: str, user_message: str, conversation_history: list[dict]
) -> dict:
    """
    呼叫 Gemini 解析自然語言訊息，回傳 intent + 結構化資料。
    conversation_history 格式：[{"role": "user"|"assistant", "content": "..."}]
    """
    member = get_member(discord_id)
    if not member:
        return {"intent": "error", "message": "請先用 /setup 註冊你的資料。"}

    context = _build_context(member, date.today())

    messages = conversation_history.copy()
    if messages and messages[0]["role"] == "user":
        messages[0]["content"] = (
            f"【目前狀態】\n{context}\n\n【使用者說】\n{messages[0]['content']}"
        )
    else:
        messages.insert(
            0,
            {
                "role": "user",
                "content": f"【目前狀態】\n{context}\n\n【使用者說】\n{user_message}",
            },
        )

    # 1. 轉換格式：將原生的 dict 陣列轉為 Gemini SDK 接受的 types.Content 陣列
    gemini_messages = []
    for msg in messages:
        # 將 Claude 的 assistant 映射到 Gemini 的 model
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_messages.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )

    # 2. 呼叫 Gemini API
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=gemini_messages,  # 放入轉換好的 gemini_messages
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1000,
            # 強制 Gemini 輸出純 JSON 格式，大幅減少格式錯誤的機率
            response_mime_type="application/json",
        ),
    )

    # 3. 取得文字回應：注意這裡是 response.text，不是 content[0].text
    raw = response.text.strip()

    # 防禦性處理：因為加了 JSON 模式，理論上不會有 markdown 標記了
    # 但保留下來作為雙重保險也無妨
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"intent": "error", "message": f"AI 回應格式錯誤：{raw}"}
