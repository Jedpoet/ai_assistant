import discord
from discord.ext import commands
from discord import app_commands
from db.database import upsert_member, get_member, get_all_members, update_preferences
from calendar.gcal import create_family_calendar
from db.database import update_calendar_id

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


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
