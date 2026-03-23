import discord
from discord.ext import commands
from discord import app_commands
from db.database import (
    upsert_member,
    get_member,
    get_member_by_name,
    get_all_members,
    update_preferences,
    update_calendar_id,
    add_fixed_schedule,
)
from gcal.gcal import create_family_calendar, add_event
from scheduler.ai import parse_message
from datetime import datetime

MEMBER_COLORS = ["#4A90D9", "#E74C3C", "#2ECC71", "#F39C12", "#9B59B6"]


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup", description="註冊家人到系統（第一次使用請先執行）"
    )
    @app_commands.describe(
        name="姓名或暱稱（例如：爸爸、小明）",
        role="身份（例如：爸爸、媽媽、小孩）",
    )
    async def setup(self, interaction: discord.Interaction, name: str, role: str = ""):
        await interaction.response.defer()

        discord_id = str(interaction.user.id)

        # 決定顏色（依照目前家人數量輪流）
        all_members = get_all_members()
        color = MEMBER_COLORS[len(all_members) % len(MEMBER_COLORS)]

        member_id = upsert_member(discord_id, name, role, color)

        # 幫這個家人建立 Google Calendar
        try:
            cal_id = create_family_calendar(f"家庭行程 - {name}")
            update_calendar_id(discord_id, cal_id)
            cal_status = "✅ Google Calendar 已建立"
        except Exception as e:
            cal_status = f"⚠️ Google Calendar 建立失敗：{e}"

        embed = discord.Embed(title="✅ 家人已註冊", color=int(color.lstrip("#"), 16))
        embed.add_field(name="姓名", value=name, inline=True)
        embed.add_field(name="身份", value=role or "未設定", inline=True)
        embed.add_field(name="日曆", value=cal_status, inline=False)
        embed.set_footer(text=f"Discord ID: {discord_id}")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="members", description="查看目前所有已註冊的家人")
    async def members(self, interaction: discord.Interaction):
        all_members = get_all_members()
        if not all_members:
            await interaction.response.send_message(
                "目前還沒有家人註冊，請用 `/setup` 開始。"
            )
            return

        embed = discord.Embed(title="👨‍👩‍👧‍👦 家人列表", color=0x4A90D9)
        for m in all_members:
            embed.add_field(
                name=f"{m['name']} ({m['role'] or '無身份'})",
                value=f"顏色：{m['color']}\n偏好：{m['preferences'] or '無'}",
                inline=True,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="preference", description="設定你的行程偏好（例如：早上不排事情）"
    )
    @app_commands.describe(text="用自然語言描述你的偏好")
    async def preference(self, interaction: discord.Interaction, text: str):
        discord_id = str(interaction.user.id)
        member = get_member(discord_id)
        if not member:
            await interaction.response.send_message(
                "請先用 `/setup` 註冊。", ephemeral=True
            )
            return

        update_preferences(discord_id, text)
        await interaction.response.send_message(
            f"✅ 偏好已更新：{text}", ephemeral=True
        )

    @app_commands.command(
        name="add_for",
        description="幫其他家人新增行程（自然語言）",
    )
    @app_commands.describe(
        member_name="目標家人的名字（例如：小明、媽媽）",
        text="用自然語言描述行程（例如：明天下午三點補習兩小時）",
    )
    async def add_for(
        self, interaction: discord.Interaction, member_name: str, text: str
    ):
        await interaction.response.defer()

        discord_id = str(interaction.user.id)
        caller = get_member(discord_id)
        if not caller:
            await interaction.followup.send("請先用 `/setup` 註冊。")
            return

        target = get_member_by_name(member_name)
        if not target:
            await interaction.followup.send(
                f"❌ 找不到叫「{member_name}」的家人，請用 `/members` 確認名字。"
            )
            return

        # 透過 AI 解析自然語言
        combined_text = f"幫{member_name}{text}"
        history = [{"role": "user", "content": combined_text}]
        result = await parse_message(discord_id, combined_text, history)

        if not result:
            await interaction.followup.send("❌ AI 解析失敗，請稍後再試。")
            return

        intent = result.get("intent")

        if intent == "add_event":
            event = result.get("event", {})
            try:
                start = datetime.fromisoformat(event["start"])
                end = datetime.fromisoformat(event["end"])
                add_event(
                    calendar_id=target["calendar_id"],
                    title=event["title"],
                    start=start,
                    end=end,
                    description=event.get("note", ""),
                )
                embed = discord.Embed(
                    title=f"✅ 已幫 {target['name']} 加入行程", color=0x2ECC71
                )
                embed.add_field(name="事件", value=event["title"], inline=False)
                embed.add_field(name="對象", value=target["name"], inline=True)
                embed.add_field(
                    name="開始",
                    value=start.strftime("%m/%d (%a) %H:%M"),
                    inline=True,
                )
                embed.add_field(
                    name="結束", value=end.strftime("%H:%M"), inline=True
                )
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ 新增失敗：{e}")

        elif intent == "add_fixed":
            fixed = result.get("fixed", {})
            try:
                DAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
                days = fixed.get("days", [])
                for day in days:
                    add_fixed_schedule(
                        member_id=target["id"],
                        title=fixed["title"],
                        day_of_week=day,
                        start_time=fixed["start_time"],
                        end_time=fixed["end_time"],
                    )
                day_str = "、".join(DAY_NAMES[d] for d in sorted(days))
                await interaction.followup.send(
                    f"✅ 已幫 {target['name']} 新增固定行程：**{fixed['title']}**\n"
                    f"📅 {day_str}  {fixed['start_time']}–{fixed['end_time']}"
                )
            except Exception as e:
                await interaction.followup.send(f"❌ 新增失敗：{e}")

        elif intent == "ask":
            await interaction.followup.send(f"🤔 {result['context']}")

        else:
            await interaction.followup.send(
                f"❌ {result.get('message', result.get('context', '未知錯誤'))}"
            )


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
