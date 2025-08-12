import discord
from discord.ext import commands

import random
import asyncio
import io

import sqlite3

import platform
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects

# --- 상수 정의 ---
DB_FILE = "lane_stats.db"
LANE_NAMES = ["top", "jungle", "mid", "bot", "support"]
LANE_EMOJIS = {"top": "⬆️", "jungle": "🌳", "mid": "➡️", "bot": "⬇️", "support": "❤️"}
LANE_CHOICES = {"탑": "top", "정글": "jungle", "미드": "mid", "원딜": "bot", "서폿": "support", "상관없음": "any"}

# --- Matplotlib 한글 폰트 설정 ---
if platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')
elif platform.system() == 'Darwin':
    plt.rc('font', family='AppleGothic')
else:
    plt.rc('font', family='NanumGothic')
plt.rcParams['axes.unicode_minus'] = False

# --- 데이터베이스 설정 ---
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lane_stats (
        user_id INTEGER PRIMARY KEY, top INTEGER DEFAULT 0, jungle INTEGER DEFAULT 0, mid INTEGER DEFAULT 0,
        bot INTEGER DEFAULT 0, support INTEGER DEFAULT 0, fixed INTEGER DEFAULT 0
    )""")
    try:
        cursor.execute("ALTER TABLE lane_stats ADD COLUMN fixed INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

# --- 1단계: 멤버 모집 View ---
class RecruitmentView(discord.ui.View):
    def __init__(self, host: discord.User):
        super().__init__(timeout=120.0)
        self.host = host
        self.participants = {host}
        self.message: discord.Message = None

    def create_recruitment_embed(self) -> discord.Embed:
        embed = discord.Embed(title="⚔️ 협곡의 전사들을 모집합니다! ⚔️", color=discord.Color.gold())
        embed.description = (f"`!랜덤라인`을 요청한 **{self.host.mention}** 님을 포함하여\n총 5명의 파티원을 모집합니다.\n\n"
                             f"**현재 참가자 ({len(self.participants)}/5)**\n" + "\n".join([p.mention for p in self.participants]))
        embed.set_footer(text="2분 안에 5명이 모이지 않으면 자동으로 취소됩니다.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "cancel_button" and interaction.user.id != self.host.id:
            await interaction.response.send_message("파티를 모집한 호스트만 취소할 수 있습니다.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="참가하기", style=discord.ButtonStyle.primary, custom_id="join_button")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants:
            return await interaction.response.send_message("이미 참여하셨습니다!", ephemeral=True)
        self.participants.add(interaction.user)
        
        if len(self.participants) == 5:
            self.stop()
        
        await interaction.response.edit_message(embed=self.create_recruitment_embed())

    @discord.ui.button(label="취소", style=discord.ButtonStyle.danger, custom_id="cancel_button")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.participants.clear()
        self.stop()
        embed = discord.Embed(title="🚫 모집 취소 🚫", description="호스트에 의해 모집이 취소되었습니다.", color=discord.Color.dark_red())
        await interaction.response.edit_message(embed=embed, view=None)

# --- 2단계: 포지션 선택 View (UI 안정성 확보) ---
class PositionSelectionView(discord.ui.View):
    def __init__(self, host: discord.User, participants: set, original_message: discord.Message):
        super().__init__(timeout=300.0)
        self.host = host
        self.participants = participants
        self.message = original_message
        self.selections = {}
        self.start_button.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        is_host_button = interaction.data.get("custom_id") in ["cancel_button", "start_button"]
        if is_host_button and interaction.user.id != self.host.id:
            await interaction.response.send_message("호스트만 사용할 수 있는 버튼입니다.", ephemeral=True)
            return False
        elif not is_host_button and interaction.user not in self.participants:
            await interaction.response.send_message("현재 파티의 참가자만 선택할 수 있습니다.", ephemeral=True)
            return False
        return True

    def create_selection_embed(self) -> discord.Embed:
        embed = discord.Embed(title="⚔️ 포지션 선택 ⚔️", description="각자 원하는 라인을 선택해주세요.\n모두 선택이 완료되면 호스트가 'Start' 버튼을 눌러주세요.", color=discord.Color.blue())
        selection_status = "\n".join([f"{p.mention}: **{self.selections.get(p.id, '선택 대기중...')}**" for p in self.participants])
        embed.add_field(name="참가자 현황", value=selection_status)
        return embed

    async def update_view(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id.startswith("lane_"):
                child.disabled = child.label != "상관없음" and child.label in self.selections.values()
        
        self.start_button.disabled = len(self.selections) != len(self.participants)
        await interaction.response.edit_message(embed=self.create_selection_embed(), view=self)

    async def handle_lane_selection(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selections[interaction.user.id] = button.label
        await self.update_view(interaction)

    # --- UI 버튼 정의 (데코레이터 방식) ---
    @discord.ui.button(label="상관없음", style=discord.ButtonStyle.secondary, custom_id="lane_상관없음", row=0)
    async def any_button(self, i: discord.Interaction, b: discord.ui.Button): await self.handle_lane_selection(i, b)
    @discord.ui.button(label="탑", style=discord.ButtonStyle.danger, custom_id="lane_탑", row=0)
    async def top_button(self, i: discord.Interaction, b: discord.ui.Button): await self.handle_lane_selection(i, b)
    # ... (다른 라인 버튼들도 동일한 패턴)
    @discord.ui.button(label="정글", style=discord.ButtonStyle.success, custom_id="lane_정글", row=0)
    async def jungle_button(self, i, b): await self.handle_lane_selection(i, b)
    @discord.ui.button(label="미드", style=discord.ButtonStyle.primary, custom_id="lane_미드", row=0)
    async def mid_button(self, i, b): await self.handle_lane_selection(i, b)
    @discord.ui.button(label="원딜", style=discord.ButtonStyle.primary, custom_id="lane_원딜", row=0)
    async def bot_button(self, i, b): await self.handle_lane_selection(i, b)
    @discord.ui.button(label="서폿", style=discord.ButtonStyle.secondary, custom_id="lane_서폿", row=1)
    async def support_button(self, i, b): await self.handle_lane_selection(i, b)
    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, custom_id="start_button", row=1)
    async def start_button(self, i: discord.Interaction, b: discord.ui.Button):
        self.stop(); await i.response.defer()
    @discord.ui.button(label="취소", style=discord.ButtonStyle.danger, custom_id="cancel_button", row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.selections.clear(); self.stop()
        embed = discord.Embed(title="🚫 모집 취소 🚫", description="호스트에 의해 모집이 취소되었습니다.", color=discord.Color.dark_red())
        await interaction.response.edit_message(embed=embed, view=None)

# --- 메인 Cog 클래스 ---
class RandomLaneCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        setup_database()

    def _get_or_create_user_stats(self, user_id: int) -> tuple:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT top, jungle, mid, bot, support, fixed FROM lane_stats WHERE user_id = ?", (user_id,))
        stats = cursor.fetchone()
        if stats:
            conn.close()
            return stats
        else:
            cursor.execute("INSERT INTO lane_stats (user_id) VALUES (?)", (user_id,))
            conn.commit()
            conn.close()
            return (0, 0, 0, 0, 0, 0)

    def _update_lane_stats(self, user_id: int, lane_to_update: str):
        if lane_to_update not in LANE_NAMES + ["fixed"]: return
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        sql = f"UPDATE lane_stats SET {lane_to_update} = {lane_to_update} + 1 WHERE user_id = ?"
        cursor.execute(sql, (user_id,))
        conn.commit()
        conn.close()

    def _assign_lanes_final(self, selections: dict) -> dict:
        fixed_players = {uid: LANE_CHOICES[choice] for uid, choice in selections.items() if choice != "상관없음"}
        fill_player_ids = [uid for uid, choice in selections.items() if choice == "상관없음"]
        available_lanes = list(set(LANE_NAMES) - set(fixed_players.values()))
        random.shuffle(fill_player_ids)
        assignments = {}
        for user_id in fill_player_ids:
            stats = self._get_or_create_user_stats(user_id)
            total_games = sum(stats)
            weights = [(total_games - count) ** 2 + 1 for count in stats[:5]]
            lane_weights = {lane: weights[LANE_NAMES.index(lane)] for lane in available_lanes}
            if not lane_weights: break
            chosen_lane = random.choices(list(lane_weights.keys()), weights=list(lane_weights.values()), k=1)[0]
            assignments[user_id] = chosen_lane
            available_lanes.remove(chosen_lane)
        final_assignments = {**fixed_players, **assignments}
        return final_assignments

    @commands.command(name='랜덤라인', help='5인 팀의 라인을 선택 또는 랜덤으로 정해줍니다.')
    async def random_lane(self, ctx: commands.Context):
        recruitment_view = RecruitmentView(host=ctx.author)
        message = await ctx.send(embed=recruitment_view.create_recruitment_embed(), view=recruitment_view)
        recruitment_view.message = message
        
        timed_out = await recruitment_view.wait()
        if timed_out:
            fail_embed = discord.Embed(title="😥 멤버 모집 실패 😥", description="아쉽게도 2분 안에 5명의 파티원이 모이지 않았어요.", color=discord.Color.dark_grey())
            await message.edit(embed=fail_embed, view=None)
            return

        if len(recruitment_view.participants) != 5: # 취소된 경우
            return

        # --- 2단계 시작 ---
        position_view = PositionSelectionView(host=ctx.author, participants=recruitment_view.participants, original_message=message)
        await message.edit(embed=position_view.create_selection_embed(), view=position_view)
        
        timed_out = await position_view.wait()
        if timed_out:
            fail_embed = discord.Embed(title="😥 시간 초과 😥", description="시간 안에 포지션 선택이 완료되지 않아 취소되었습니다.", color=discord.Color.dark_grey())
            await message.edit(embed=fail_embed, view=None)
            return

        if len(position_view.selections) != 5: # 취소된 경우
            return

        # --- 최종 결과 발표 ---
        final_assignments = self._assign_lanes_final(position_view.selections)
        result_desc = []
        for user_id, lane in final_assignments.items():
            db_lane = lane if position_view.selections[user_id] == "상관없음" else "fixed"
            self._update_lane_stats(user_id, db_lane)
            result_desc.append(f"{LANE_EMOJIS.get(lane, '❔')} **{lane.capitalize()}** : <@{user_id}>")
        result_embed = discord.Embed(title="🎉 포지션 분배 완료! 🎉", description="\n".join(result_desc), color=discord.Color.green())
        await message.edit(embed=result_embed, view=None)


    # 라인 통계 명령어 ⭐️⭐️⭐️
    @commands.command(name='라인통계', help='자신의 라인별 플레이 통계를 원형 차트로 보여줍니다.')
    async def lane_stats(self, ctx):
        user = ctx.author
        stats = self._get_or_create_user_stats(user.id)

        lane_counts = stats[0:5]  # (top, jungle, mid, bot, support)
        fixed_plays = stats[5]
        random_plays = sum(lane_counts)
        total_games = random_plays + fixed_plays

        if total_games == 0:
            await ctx.send(f"{user.mention}님은 아직 플레이 기록이 없습니다. `!랜덤라인`을 통해 게임을 플레이해주세요!")
            return

        # --- 원형 차트 생성 (랜덤 플레이만 대상) ---
        labels = ['탑', '정글', '미드', '바텀', '서폿']
        # 플레이 횟수가 0인 라인은 차트에서 제외
        filtered_labels = [label for i, label in enumerate(labels) if lane_counts[i] > 0]
        filtered_counts = [count for count in lane_counts if count > 0]

        # 차트 생성 로직 
        fig, ax = plt.subplots(figsize=(8, 6), facecolor='#D4D4D4')
        ax.set_facecolor("#D4D4D4")
        text_props = {'fontsize': 14, 'color': 'white', 'fontweight': 'bold'}
        text_effects = [path_effects.withStroke(linewidth=3, foreground='black')]
        
        # 랜덤 플레이 기록이 있을 때만 차트 생성
        if random_plays > 0:
            wedges, texts, autotexts = ax.pie(
                filtered_counts, autopct='%1.1f%%', startangle=140,
                wedgeprops={'edgecolor': 'white', 'linewidth': 2}, textprops=text_props
            )
            for text in autotexts:
                text.set_path_effects(text_effects)
            ax.legend(wedges, filtered_labels, title="랜덤 라인", loc="center left", bbox_to_anchor=(0.9, 0, 0.5, 1), fontsize=12)
        else:
            ax.text(0.5, 0.5, "랜덤 플레이 기록 없음", ha='center', va='center', fontsize=16)

        ax.axis('equal')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        file = discord.File(buf, filename='stats.png')

        # --- 임베드 생성 ---
        embed = discord.Embed(
            title=f"📊 {user.display_name}님의 플레이 통계",
            description="당신이 플레이한 라인을 분석한 결과입니다.",
            color=discord.Color.purple()
        )
        embed.set_image(url="attachment://stats.png")

        # 필드 1: 랜덤 라인 분포
        distribution_text = ""
        for i in range(len(labels)):
            # 전체 게임 대비 퍼센티지 계산
            percentage = (lane_counts[i] / total_games) * 100 if total_games > 0 else 0
            distribution_text += f"{labels[i]}: {lane_counts[i]}회 ({percentage:.1f}%)\n"
        embed.add_field(name="📈 랜덤 라인 분포", value=distribution_text, inline=True)

        # 필드 2: 플레이 요약
        summary_text = (
            f"﹒랜덤 플레이: {random_plays}회\n"
            f"﹒고정 플레이: {fixed_plays}회\n"
            f"**﹒총 플레이: {total_games}회**"
        )
        embed.add_field(name="📋 플레이 요약", value=summary_text, inline=True)
        
        await ctx.send(file=file, embed=embed)
async def setup(bot):
    await bot.add_cog(RandomLaneCog(bot))