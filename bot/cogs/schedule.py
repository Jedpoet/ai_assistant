import discord
import os
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.database import (
    get_member,
    add_fixed_schedule,
    get_fixed_schedules,
    delete_fixed_schedule,
)
from scheduler.ai import parse_message
from calendar.gcal import add_event
from dotenv import load_dotenv

load_dotenv()

# 設定觸發頻道名稱（在這個頻道裡不需要 @mention）
SCHEDULE_CHANNEL_ID = os.getenv("SCHEDULE_CHANNEL_ID")

# 每個 discord_id 的多輪對話暫存（重啟後清空）
_sessions: dict[str, list[dict]] = {}

DAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


class ScheduleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── 自然語言監聽 ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 忽略 Bot 自己的訊息
        if message.author.bot:
            return

        is_schedule_channel = message.channel.id == SCHEDULE_CHANNEL_ID
        is_mentioned = self.bot.user in message.mentions

        if not is_schedule_channel and not is_mentioned:
            return

        # 去掉 @mention 前綴，取得純文字
        text = message.content
        if is_mentioned:
            text = text.replace(f"<@{self.bot.user.id}>", "").strip()
        if not text:
            return

        discord_id = str(message.author.id)
        member = get_member(discord_id)
        if not member:
            await message.reply("請先用 `/setup` 註冊你的資料。")
            return

        async with message.channel.typing():
            history = _sessions.get(discord_id, [])
            history.append({"role": "user", "content": text})
            result = parse_message(discord_id, text, history)

        await self._handle_result(message, discord_id, member, result, history)

    async def _handle_result(
        self,
        message: discord.Message,
        discord_id: str,
        member,
        result: dict,
        history: list[dict],
    ):
        intent = result.get("intent")

        # ── 一次性事件 ──
        if intent == "add_event":
            event = result.get("event", {})
            try:
                start = datetime.fromisoformat(event["start"])
                end = datetime.fromisoformat(event["end"])
                add_event(
                    calendar_id=member["calendar_id"],
                    title=event["title"],
                    start=start,
                    end=end,
                    description=event.get("note", ""),
                )
                _sessions.pop(discord_id, None)  # 任務完成，清除對話

                embed = discord.Embed(title="✅ 行程已加入", color=0x2ECC71)
                embed.add_field(name="事件", value=event["title"], inline=False)
                embed.add_field(
                    name="開始", value=start.strftime("%m/%d (%a) %H:%M"), inline=True
                )
                embed.add_field(name="結束", value=end.strftime("%H:%M"), inline=True)
                if event.get("note"):
                    embed.add_field(name="備註", value=event["note"], inline=False)
                await message.reply(embed=embed)

            except Exception as e:
                await message.reply(f"❌ 新增失敗：{e}")

        # ── 固定行程 ──
        elif intent == "add_fixed":
            fixed = result.get("fixed", {})
            try:
                days = fixed.get("days", [])
                for day in days:
                    add_fixed_schedule(
                        member_id=member["id"],
                        title=fixed["title"],
                        day_of_week=day,
                        start_time=fixed["start_time"],
                        end_time=fixed["end_time"],
                    )
                _sessions.pop(discord_id, None)

                day_str = "、".join(DAY_NAMES[d] for d in sorted(days))
                await message.reply(
                    f"✅ 固定行程已新增：**{fixed['title']}**\n"
                    f"📅 {day_str}  {fixed['start_time']}–{fixed['end_time']}"
                )

            except Exception as e:
                await message.reply(f"❌ 新增失敗：{e}")

        # ── 需要追問 ──
        elif intent == "ask":
            history.append({"role": "assistant", "content": result["question"]})
            _sessions[discord_id] = history
            await message.reply(f"🤔 {result['question']}")

        # ── 一般聊天，忽略 ──
        elif intent == "ignore":
            pass

        # ── 錯誤 ──
        else:
            await message.reply(f"❌ {result.get('message', '未知錯誤')}")

    # ── Slash 指令：固定行程管理 ─────────────────────────────

    @app_commands.command(name="fixed_list", description="查看你的固定行程")
    async def fixed_list(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        member = get_member(discord_id)
        if not member:
            await interaction.response.send_message(
                "請先用 `/setup` 註冊。", ephemeral=True
            )
            return

        schedules = get_fixed_schedules(member["id"])
        if not schedules:
            await interaction.response.send_message("目前沒有固定行程。")
            return

        lines = [
            f"`{s['id']}` {DAY_NAMES[s['day_of_week']]} {s['start_time']}–{s['end_time']}  **{s['title']}**"
            for s in schedules
        ]
        embed = discord.Embed(
            title=f"📅 {member['name']} 的固定行程",
            description="\n".join(lines),
            color=int(member["color"].lstrip("#"), 16),
        )
        embed.set_footer(text="用 /fixed_remove <id> 刪除")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="fixed_remove", description="刪除一筆固定行程")
    @app_commands.describe(schedule_id="固定行程 ID（從 /fixed_list 查詢）")
    async def fixed_remove(self, interaction: discord.Interaction, schedule_id: int):
        delete_fixed_schedule(schedule_id)
        await interaction.response.send_message(f"✅ 已刪除固定行程 ID {schedule_id}")


async def setup(bot):
    await bot.add_cog(ScheduleCog(bot))
