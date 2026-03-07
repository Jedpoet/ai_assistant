import discord
from discord.ext import commands
from discord import app_commands
from datetime import date, timedelta, datetime
import io
from db.database import get_all_members, get_fixed_schedules
from calendar.gcal import get_events_for_week
from image.week_chart import generate_week_image


def _get_week_start(offset: int = 0) -> date:
    """offset=0 本週, offset=1 下週"""
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


class WeekCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="week", description="生成本週（或下週）全家行程圖")
    @app_commands.describe(next_week="True = 顯示下週，False = 顯示本週（預設）")
    async def week(self, interaction: discord.Interaction, next_week: bool = False):
        await interaction.response.defer()

        week_start = _get_week_start(1 if next_week else 0)
        all_members = get_all_members()

        if not all_members:
            await interaction.followup.send("還沒有家人資料，請先用 `/setup` 註冊。")
            return

        members_data = []
        for m in all_members:
            events = []

            # 固定行程
            for fs in get_fixed_schedules(m["id"]):
                events.append(
                    {
                        "title": fs["title"],
                        "day": fs["day_of_week"],
                        "start": fs["start_time"],
                        "end": fs["end_time"],
                    }
                )

            # Google Calendar 動態事件
            if m["calendar_id"]:
                try:
                    for e in get_events_for_week(m["calendar_id"], week_start):
                        start_dt = datetime.fromisoformat(
                            e["start"].replace("Z", "+00:00")
                        )
                        end_dt = datetime.fromisoformat(e["end"].replace("Z", "+00:00"))
                        day_idx = (start_dt.date() - week_start).days
                        if 0 <= day_idx < 7:
                            events.append(
                                {
                                    "title": e["title"],
                                    "day": day_idx,
                                    "start": start_dt.strftime("%H:%M"),
                                    "end": end_dt.strftime("%H:%M"),
                                }
                            )
                except Exception as e:
                    pass  # Google Calendar 讀取失敗時跳過，不中斷整個指令

            members_data.append(
                {
                    "name": m["name"],
                    "color": m["color"],
                    "events": events,
                }
            )

        # 生成圖片
        png_bytes = generate_week_image(members_data, week_start)
        week_end = week_start + timedelta(days=6)
        filename = f"week_{week_start.strftime('%m%d')}.png"

        await interaction.followup.send(
            content=f"📅 **{'下週' if next_week else '本週'}行程** {week_start.month}/{week_start.day} – {week_end.month}/{week_end.day}",
            file=discord.File(io.BytesIO(png_bytes), filename=filename),
        )


async def setup(bot):
    await bot.add_cog(WeekCog(bot))
