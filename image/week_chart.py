import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from datetime import date, timedelta, datetime
import io
from matplotlib import patheffects as path_effects

DAY_LABELS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
HOUR_START = 7  # 圖表顯示從幾點開始
HOUR_END = 23  # 圖表顯示到幾點結束


def _time_to_hour(time_str: str) -> float:
    """'HH:MM' or ISO8601 → float hour"""
    if "T" in time_str:
        dt = datetime.fromisoformat(time_str)
        return dt.hour + dt.minute / 60
    h, m = map(int, time_str.split(":"))
    return h + m / 60


def generate_week_image(members: list[dict], week_start: date) -> bytes:
    """
    members 格式：
    [
      {
        "name": "爸爸",
        "color": "#4A90D9",
        "events": [
          {"title": "上班", "day": 0, "start": "09:00", "end": "18:00"},
          ...
        ]
      },
      ...
    ]
    回傳 PNG bytes。
    """
    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(10, 16))
    fig.patch.set_facecolor("#F0F2F5")
    ax.set_facecolor("#F0F2F5")

    num_days = 7
    hour_range = HOUR_END - HOUR_START

    # 格線
    for d in range(num_days + 1):
        ax.axvline(x=d, color="#CED4DA", linewidth=1.0)
    for h in range(hour_range + 1):
        ax.axhline(y=h, color="#CED4DA", linewidth=0.5)

    # 時間軸標籤
    ax.set_yticks(range(hour_range + 1))
    ax.set_yticklabels(
        [f"{HOUR_START + h:02d}:00" for h in range(hour_range + 1)],
        fontsize=11,
        color="#212529",
    )
    ax.yaxis.set_tick_params(length=0)

    # 日期欄標籤
    ax.set_xticks([d + 0.5 for d in range(num_days)])
    day_labels = []
    for d in range(num_days):
        day = week_start + timedelta(days=d)
        day_labels.append(f"{DAY_LABELS[d]}\n{day.month}/{day.day}")
    ax.set_xticklabels(day_labels, fontsize=11, fontweight="bold", color="#4A90D9")
    ax.xaxis.set_tick_params(length=0)

    ax.set_xlim(0, num_days)
    ax.set_ylim(hour_range, 0)  # y 軸翻轉，上方為早

    # 每個家人的事件（多人同天稍微錯開）
    member_count = len(members)
    bar_width = 0.82 / max(member_count, 1)

    for m_idx, member in enumerate(members):
        color = member.get("color", "#4A90D9")
        x_offset = 0.09 + m_idx * bar_width

        for event in member.get("events", []):
            d = event["day"]  # 0=週一
            y_start = _time_to_hour(event["start"]) - HOUR_START
            y_end = _time_to_hour(event["end"]) - HOUR_START
            height = y_end - y_start

            if height <= 0:
                continue

            rect = FancyBboxPatch(
                (d + x_offset, y_start),
                bar_width - 0.04,
                height,
                boxstyle="round,pad=0.02",
                facecolor=color,
                edgecolor="white",
                linewidth=1.5,
                alpha=1.0,
                zorder=3,
            )
            ax.add_patch(rect)

            # 事件標題
            font_size = 9 if height < 0.6 else 11
            label = (
                f"{member['name']}\n{event['title']}"
                if member_count > 1
                else event["title"]
            )
            txt = ax.text(
                d + x_offset + (bar_width - 0.04) / 2,
                y_start + height / 2,
                label,
                ha="center",
                va="center",
                fontsize=font_size,
                color="black",
                fontweight="bold",
                clip_on=True,
                zorder=4,
            )
            txt.set_path_effects(
                [
                    path_effects.Stroke(linewidth=2, foreground="black", alpha=0.45),
                    path_effects.Normal(),
                ]
            )

    # 今天高亮
    today = date.today()
    if week_start <= today < week_start + timedelta(days=7):
        today_idx = (today - week_start).days
        ax.axvspan(today_idx, today_idx + 1, alpha=0.07, color="#FFC107", zorder=0)

    # 圖例
    legend_patches = [
        mpatches.Patch(color=m["color"], label=m["name"], alpha=0.85) for m in members
    ]
    ax.legend(
        handles=legend_patches,
        loc="upper right",
        framealpha=0.95,
        fontsize=11,
        title="家人",
        title_fontsize=11,
    )

    # 標題
    week_end = week_start + timedelta(days=6)
    ax.set_title(
        f"家庭週行程  {week_start.month}/{week_start.day} – {week_end.month}/{week_end.day}",
        fontsize=15,
        fontweight="bold",
        color="#212529",
        pad=14,
    )

    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
