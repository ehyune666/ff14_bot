import os
import datetime
import json
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import tasks, commands

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 절대 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAVORITES_FILE = os.path.join(BASE_DIR, "favorites.json")
SERVERS_FILE = os.path.join(BASE_DIR, "server_channels.json")

# 파판14 전장 사이클 (8일 기준)
MAP_CYCLE = [
    "봉바",
    "쇄빙",
    "온살",
    "워코",
    "봉바",
    "제압",
    "온살",
    "워코"
]

# 오늘 기준 전장 설정 (2026년 9월 2일 = 워코)
BASE_DATE = datetime.date(2026, 9, 2)
BASE_INDEX = 3  # 워코

# 유저별 즐겨찾기 저장/불러오기 { "user_id_str": ["쇄빙", "제압"] }
def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                elif isinstance(data, list):
                    return {}
        except Exception:
            return {}
    return {}

def save_favorites(favorites_dict):
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites_dict, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"즐겨찾기 파일 저장 중 오류 발생: {e}")

# 서버별 알림 채널 저장/불러오기 { "guild_id_str": channel_id_int }
def load_server_channels():
    if os.path.exists(SERVERS_FILE):
        try:
            with open(SERVERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
    return {}

def save_server_channels(servers_dict):
    try:
        with open(SERVERS_FILE, "w", encoding="utf-8") as f:
            json.dump(servers_dict, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"서버 채널 파일 저장 중 오류 발생: {e}")

def get_today_map(target_date=None):
    if target_date is None:
        target_date = datetime.date.today()
    delta_days = (target_date - BASE_DATE).days
    current_index = (BASE_INDEX + delta_days) % len(MAP_CYCLE)
    return MAP_CYCLE[current_index]

def get_upcoming_schedule(days=8):
    today = datetime.date.today()
    schedule = []
    for day in range(days):
        future_date = today + datetime.timedelta(days=day)
        map_name = get_today_map(future_date)
        schedule.append((future_date, map_name))
    return schedule

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    if not daily_notification.is_running():
        daily_notification.start()

# 매일 오전 12시(00:00 KST) 모든 등록 서버로 자동 알림 전송
@tasks.loop(time=datetime.time(hour=0, minute=0, second=0))
async def daily_notification():
    server_channels = load_server_channels()
    all_favorites = load_favorites()
    today_map = get_today_map()

    for guild_id_str, channel_id in server_channels.items():
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                # 기본 오늘의 전장 안내
                await channel.send(f"오늘의 전장은 **{today_map}**입니다!")
                
                # 해당 서버에 속해있으면서 오늘 전장을 즐겨찾기한 유저 탐색
                target_users = []
                for user_id_str, user_favs in all_favorites.items():
                    if today_map in user_favs:
                        member = channel.guild.get_member(int(user_id_str))
                        if member:
                            target_users.append(f"<@{user_id_str}>")
                
                if target_users:
                    mentions = ", ".join(target_users)
                    await channel.send(f"🔔 {mentions} 님! 오늘은 설정하신 **{today_map}** 데이입니다!")
            except Exception as e:
                print(f"채널 {channel_id} 전송 실패: {e}")

@bot.tree.command(name="오늘전장", description="오늘의 전장 정보를 확인합니다.")
async def today_map_cmd(interaction: discord.Interaction):
    today_map = get_today_map()
    await interaction.response.send_message(f"오늘의 전장은 **{today_map}**입니다!")

@bot.tree.command(name="전장일정", description="향후 8일간의 전체 전장 일정을 확인합니다.")
async def schedule_cmd(interaction: discord.Interaction):
    schedule = get_upcoming_schedule(8)
    
    embed = discord.Embed(
        title="📅 파이널판타지14 전장 8일 전체 일정",
        color=discord.Color.gold()
    )
    
    for date_obj, map_name in schedule:
        date_str = date_obj.strftime("%m월 %d일")
        day_label = "오늘" if date_obj == datetime.date.today() else f"{(date_obj - datetime.date.today()).days}일 뒤"
        embed.add_field(
            name=f"{date_str} ({day_label})",
            value=f"**{map_name}**",
            inline=False
        )
        
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="알림일정", description="내가 알림 설정한 전장들의 향후 한 달(30일) 일정을 확인합니다.")
async def fav_schedule_cmd(interaction: discord.Interaction):
    all_favorites = load_favorites()
    user_id_str = str(interaction.user.id)
    user_favs = all_favorites.get(user_id_str, [])

    if not user_favs:
        await interaction.response.send_message("현재 등록된 알림 전장이 없습니다. `/알림설정` 명령어로 먼저 등록해 보세요!", ephemeral=True)
        return

    today = datetime.date.today()
    schedule = {fav: [] for fav in user_favs}
    
    for day in range(30):
        future_date = today + datetime.timedelta(days=day)
        map_name = get_today_map(future_date)
        if map_name in schedule:
            schedule[map_name].append(future_date)

    embed = discord.Embed(
        title=f"🔔 {interaction.user.display_name}님의 알림 설정 전장 (30일 일정)",
        color=discord.Color.blue()
    )

    for map_name, dates in schedule.items():
        if dates:
            date_list_str = "\n".join([
                f"• {d.strftime('%m월 %d일')} ({'오늘' if d == today else f'{(d - today).days}일 뒤'})"
                for d in dates
            ])
            embed.add_field(name=f"⚔️ {map_name}", value=date_list_str, inline=True)
        else:
            embed.add_field(name=f"⚔️ {map_name}", value="30일 내 일정 없음", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="알림설정", description="특정 전장이 열리는 날 추가 알림을 받도록 등록합니다.")
@app_commands.describe(map_name="알림을 받고 싶은 전장 이름 (예: 쇄빙, 제압, 봉바, 워코, 온살)")
async def add_favorite_cmd(interaction: discord.Interaction, map_name: str):
    if map_name not in MAP_CYCLE:
        valid_maps = ", ".join(set(MAP_CYCLE))
        await interaction.response.send_message(f"❌ 올바른 전장 이름을 입력해 주세요. (가능한 전장: {valid_maps})", ephemeral=True)
        return

    all_favorites = load_favorites()
    user_id_str = str(interaction.user.id)
    user_favs = all_favorites.get(user_id_str, [])

    if map_name in user_favs:
        await interaction.response.send_message(f"⚠️ 이미 **{map_name}** 알림이 설정되어 있습니다!", ephemeral=True)
    else:
        user_favs.append(map_name)
        all_favorites[user_id_str] = user_favs
        save_favorites(all_favorites)
        await interaction.response.send_message(f"✅ **{map_name}** 알림이 등록되었습니다! 해당 전장이 열리는 날 추가 알림이 발송됩니다.", ephemeral=True)

@bot.tree.command(name="알림해제", description="등록했던 특정 전장 알림을 해제합니다.")
@app_commands.describe(map_name="알림을 해제할 전장 이름 (예: 쇄빙, 제압)")
async def remove_favorite_cmd(interaction: discord.Interaction, map_name: str):
    all_favorites = load_favorites()
    user_id_str = str(interaction.user.id)
    user_favs = all_favorites.get(user_id_str, [])

    if map_name in user_favs:
        user_favs.remove(map_name)
        all_favorites[user_id_str] = user_favs
        save_favorites(all_favorites)
        await interaction.response.send_message(f"🗑️ **{map_name}** 알림이 해제되었습니다.", ephemeral=True)
    else:
        await interaction.response.send_message("등록되어 있지 않은 전장입니다.", ephemeral=True)

@bot.tree.command(name="알림목록", description="내가 현재 등록한 특정 전장 알림 목록을 확인합니다.")
async def list_favorites_cmd(interaction: discord.Interaction):
    all_favorites = load_favorites()
    user_id_str = str(interaction.user.id)
    user_favs = all_favorites.get(user_id_str, [])

    if user_favs:
        fav_str = ", ".join(user_favs)
        await interaction.response.send_message(f"🔔 현재 알림 설정된 전장: **{fav_str}**", ephemeral=True)
    else:
        await interaction.response.send_message("현재 등록된 특정 전장 알림이 없습니다. `/알림설정` 명령어로 등록해 보세요!", ephemeral=True)

@bot.tree.command(name="알림채널설정", description="[관리자 전용] 이 채널을 매일 자정 전장 알림 채널로 지정합니다.")
@app_commands.checks.has_permissions(manage_channels=True)
async def set_channel_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("서버 채널에서만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return

    servers_dict = load_server_channels()
    guild_id_str = str(interaction.guild.id)
    servers_dict[guild_id_str] = interaction.channel_id
    save_server_channels(servers_dict)

    await interaction.response.send_message(f"✅ **{interaction.channel.name}** 채널이 매일 자정 자동 알림 채널로 설정되었습니다!")

@set_channel_error_handler := set_channel_cmd.error
async def set_channel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 이 명령어를 사용하려면 '채널 관리' 권한이 필요합니다.", ephemeral=True)

@bot.tree.command(name="알림채널해제", description="[관리자 전용] 현재 서버의 매일 자정 자동 알림 채널 설정을 해제합니다.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unset_channel_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("서버 채널에서만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return

    servers_dict = load_server_channels()
    guild_id_str = str(interaction.guild.id)

    if guild_id_str in servers_dict:
        del servers_dict[guild_id_str]
        save_server_channels(servers_dict)
        await interaction.response.send_message("🗑️ 자동 알림 채널 설정이 해제되었습니다.")
    else:
        await interaction.response.send_message("설정되어 있는 자동 알림 채널이 없습니다.", ephemeral=True)

@unset_channel_error_handler := unset_channel_cmd.error
async def unset_channel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 이 명령어를 사용하려면 '채널 관리' 권한이 필요합니다.", ephemeral=True)

# --------------------------------------------------
# 봇 개발자(소유자) 전용 서버 수 확인 명령어 (최적화 버전)
# --------------------------------------------------
@bot.tree.command(name="서버수", description="[봇 개발자 전용] 현재 봇이 참여 중인 총 서버 수를 확인합니다.")
async def server_count_cmd(interaction: discord.Interaction):
    is_owner = await bot.is_owner(interaction.user)
    if not is_owner:
        await interaction.response.send_message("❌ 이 명령어는 봇 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    count = len(bot.guilds)
    await interaction.response.send_message(f"🌐 현재 봇이 참여 중인 서버는 총 **{count}개**입니다.", ephemeral=True)

bot.run(TOKEN)