# 家庭行程助理 Discord Bot

## 架構

```
Discord Bot（slash commands）
        ↓
    對話管理 + 用戶識別（Discord ID → 家人）
        ↓
    Claude API（解析意圖、找空檔、決定問什麼）
        ↓
  SQLite（家人 profile + 固定行程）+ Google Calendar API（動態事件）
        ↓
    Matplotlib（生成週行程圖片）
```

## 安裝

```bash
pip install -r requirements.txt
cp .env.example .env
# 編輯 .env，填入各項 token
```

## 設定步驟

### 1. Discord Bot Token
1. 前往 https://discord.com/developers/applications
2. 建立新 Application → Bot → 複製 Token
3. 開啟 `MESSAGE CONTENT INTENT`
4. 邀請 Bot 到你的 Discord Server（需要 `bot` + `applications.commands` scope）

### 2. Anthropic API Key
前往 https://console.anthropic.com 取得 API Key

### 3. Google Calendar API
1. 前往 https://console.cloud.google.com
2. 建立專案 → 啟用 **Google Calendar API**
3. 建立 OAuth 2.0 憑證（類型：桌面應用程式）
4. 下載 JSON → 存為 `credentials.json`
5. 第一次執行時會開啟瀏覽器授權，之後自動使用 `token.json`

## 啟動

```bash
python main.py
```

## Discord 指令

| 指令 | 說明 |
|------|------|
| `/setup name:爸爸 role:爸爸` | 第一次使用，註冊家人 |
| `/members` | 查看所有已註冊家人 |
| `/preference text:早上不排事情` | 設定行程偏好 |
| `/add text:下週四下午兩點看牙醫一小時` | 自然語言新增行程 |
| `/add_for member_name:小明 text:明天下午三點補習兩小時` | 幫其他家人新增行程 |
| `/fixed_add title:學校 day:0 start:08:00 end:17:00` | 新增每週固定行程 |
| `/fixed_list` | 查看固定行程 |
| `/fixed_remove schedule_id:3` | 刪除固定行程 |
| `/week` | 生成本週全家行程圖 |
| `/week next_week:True` | 生成下週全家行程圖 |

## 使用流程範例

1. 每個家人各自執行 `/setup`
2. 用 `/fixed_add` 輸入課表、班表等固定行程
3. 臨時行程用 `/add` 加入（Bot 會問你缺少的資訊）
4. 隨時用 `/week` 看全家這週的行程圖
5. 在行程頻道輸入「幫小明下週三下午看醫生一小時」，Bot 會自動幫小明新增行程
6. 也可以用 `/add_for member_name:小明 text:明天補習兩小時` 幫家人排行程

