import os
import json
from datetime import date, timedelta
from sys import exc_info, exception
from google import genai
from google.genai import types
from db.database import get_fixed_schedules, get_member, get_all_members
from gcal.gcal import get_events_for_week
from dotenv import load_dotenv
import asyncio

load_dotenv()

client = genai.Client()

DAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def _build_context(member_row, today: date) -> str:
    """組出注入給 Gemini 的當前狀態 context"""
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

    # 家人名單（供 AI 辨識 for_member）
    all_members = get_all_members()
    family_list = "、".join(m["name"] for m in all_members)

    return f"""今天日期：{today.strftime("%Y-%m-%d")} ({DAY_NAMES[today.weekday()]})
本週開始：{week_start.strftime("%Y-%m-%d")}
目前使用者：{member_row["name"]}
已註冊家人：{family_list}

{member_row["name"]} 的固定行程（每週重複）：
{fixed_text}

{member_row["name"]} 的本週動態事件：
{dynamic_text}

使用者偏好：{preferences}"""


SYSTEM_PROMPT = """你是一個家庭行程助理，負責解析使用者的自然語言並決定要執行的動作。

## Intent 說明

- **add_event**：一次性事件（例如：「下週四看牙醫」、「明天下午開會兩小時」）
- **add_fixed**：每週固定重複的行程（例如：「我每週一到五早上八點上班到五點」、「週三晚上七點鋼琴課一小時」）
- **ask**：使用者說的是行程相關的事，但缺少必要資訊（時間、日期或時長），需要追問
- **chat**：與行程無關的一般聊天

## 幫其他家人安排行程

- 當使用者提到「幫 XXX」、「替 XXX」、「給 XXX」等字眼時，代表要幫另一位家人安排行程。
- 在 context 中會列出「已註冊家人」名單，請從中比對名字。
- 如果名字不在名單中，用 ask 回覆告知找不到該家人，並列出有哪些家人可選。
- 如果未提及為誰安排，則 for_member 欄位不要填寫（代表幫自己）。

## 規則

1. 只輸出 JSON，不要加任何說明文字或 markdown。
2. 避免與固定行程或已有事件衝突；若有衝突，改用 ask 告知使用者。
3. 時間使用 ISO 8601（例如 2024-03-15T14:00:00）。
4. 固定行程的 days 為陣列，0=週一…6=週日。
5. 如果是整天的行程，設定從0:00~23:59

## 回傳格式

```
{
  "intent": "add_event" | "add_fixed" | "ask" | "chat",

  // 選填：幫其他家人安排時填入對方的名字，幫自己時省略此欄位
  "for_member": "家人名字",

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

  // intent=ask or intent=chat 時：
  "context": "用繁體中文問使用者缺少的資訊或回覆聊天"
}
```
"""


async def parse_message(
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

    max_retries = 3
    # 2. 呼叫 Gemini API
    base_delay = 2  # 基礎等待時間為 2 秒

    for attempt in range(max_retries):
        try:
            # 💡 針對 Discord 的非同步環境，建議使用 client.aio
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=gemini_messages,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=1000,
                    response_mime_type="application/json",
                ),
            )
            if hasattr(response, "text"):
                raw = response.text.strip()
            elif isinstance(response, str):
                raw = response.strip()
            else:
                return {"intent": "error", "message": f"AI 回應格式錯誤：\n{response}"}

        except errors.ServerError as e:
            # 如果是 503 等伺服器端錯誤，進行捕捉
            if attempt == max_retries - 1:
                # 如果已經是最後一次重試，就放棄並回傳 None
                print(f"[Error] Gemini API 持續無回應，已達最大重試次數: {e}")
                return None

            # 計算指數退避時間：2秒 -> 4秒 -> 8秒
            wait_time = base_delay * (2**attempt)
            print(
                f"[Warning] 遇到 503 錯誤，伺服器忙碌中。等待 {wait_time} 秒後進行第 {attempt + 1} 次重試..."
            )
            await asyncio.sleep(wait_time)

        except Exception as e:
            # 捕捉 503 以外的其他例外狀況（例如網路斷線、Token 格式錯誤等）
            print(f"[Error] 發生未預期的錯誤: {e}")
            return None

    # 3. 取得文字回應：注意這裡是 response.text，不是 content[0].text
    print("raw: ", raw)

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
