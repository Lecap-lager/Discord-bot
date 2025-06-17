import discord
from discord.ext import commands

import random
import asyncio
import io
import sqlite3
import platform
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects

# --- 상수 정의 (구조화하여 통합) ---
DB_FILE = "lane_stats.db"

# --- 변경점 --- : 관련된 상수들을 하나의 딕셔너리로 묶어 관리 용이성 증대
LANE_DATA = {
    "top":    {"korean": "탑", "emoji": "⬆️", "style": discord.ButtonStyle.danger},
    "jungle": {"korean": "정글", "emoji": "🌳", "style": discord.ButtonStyle.success},
    "mid":    {"korean": "미드", "emoji": "➡️", "style": discord.ButtonStyle.primary},
    "bot":    {"korean": "원딜", "emoji": "⬇️", "style": discord.ButtonStyle.primary},
    "support":{"korean": "서폿", "emoji": "❤️", "style": discord.ButtonStyle.secondary},
}
LANE_NAMES = list(LANE_DATA.keys())
LANE_CHOICES = {data["korean"]: lane for lane, data in LANE_DATA.items()}
LANE_CHOICES["상관없음"] = "any"


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
    with sqlite3.connect(DB_FILE) as conn: 
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lane_stats (
            user_id INTEGER PRIMARY KEY, top INTEGER DEFAULT 0, jungle INTEGER DEFAULT 0, mid INTEGER DEFAULT 0,
            bot INTEGER DEFAULT 0, support INTEGER DEFAULT 0, fixed INTEGER DEFAULT 0
        )""")
        conn.commit()

# --- 1단계: 멤버 모집 View  ---
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
        self.stop()
        embed = discord.Embed(title="🚫 모집 취소 🚫", description="호스트에 의해 모집이 취소되었습니다.", color=discord.Color.dark_red())
        await interaction.response.edit_message(embed=embed, view=None)

# --- 2단계: 포지션 선택 View ---
class PositionSelectionView(discord.ui.View):
    def __init__(self, host: discord.User, participants: set):
        super().__init__(timeout=300.0)
        self.host = host
        self.participants = participants
        self.selections = {} # {user_id: "탑", ...}

        # '상관없음' 버튼 추가
        self.add_item(self.create_lane_button("any"))
        
        # 각 라인 버튼 동적 추가
        for i, lane_name in enumerate(LANE_NAMES):
            self.add_item(self.create_lane_button(lane_name, row=(i // 4) + 1))
            
        # 호스트 전용 버튼 추가
        self.add_item(self.start_button)
        self.add_item(self.cancel_button)
        self.start_button.disabled = True

    def create_lane_button(self, lane_key: str, row: int = 0) -> discord.ui.Button:
        if lane_key == "any":
            label = "상관없음"
            style = discord.ButtonStyle.secondary
        else:
            label = LANE_DATA[lane_key]["korean"]
            style = LANE_DATA[lane_key]["style"]

        button = discord.ui.Button(label=label, style=style, custom_id=f"lane_{label}", row=row)

        button.callback = self.handle_lane_selection
        return button

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        custom_id = interaction.data.get("custom_id")
        
        if custom_id.startswith("lane_"): # 라인 선택 버튼
            if user not in self.participants:
                await interaction.response.send_message("현재 파티의 참가자만 선택할 수 있습니다.", ephemeral=True)
                return False
        elif custom_id in ["start_button", "cancel_button"]: # 호스트 전용 버튼
            if user.id != self.host.id:
                await interaction.response.send_message("호스트만 사용할 수 있는 버튼입니다.", ephemeral=True)
                return False
        return True

    def create_selection_embed(self) -> discord.Embed:
        embed = discord.Embed(title="⚔️ 포지션 선택 ⚔️", description="각자 원하는 라인을 선택해주세요.\n모두 선택이 완료되면 호스트가 'Start' 버튼을 눌러주세요.", color=discord.Color.blue())
        selection_status = "\n".join([f"{p.mention}: **{self.selections.get(p.id, '선택 대기중...')}**" for p in self.participants])
        embed.add_field(name="참가자 현황", value=selection_status)
        return embed

    async def update_view_and_message(self, interaction: discord.Interaction):
        # 이미 선택된 고정 라인 목록
        chosen_lanes = {choice for choice in self.selections.values() if choice != "상관없음"}

        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id.startswith("lane_"):
                # '상관없음'이 아니면서, 다른 사람이 이미 선택한 라인은 비활성화
                child.disabled = (child.label != "상관없음" and child.label in chosen_lanes)
        
        self.start_button.disabled = len(self.selections) != len(self.participants)
        await interaction.response.edit_message(embed=self.create_selection_embed(), view=self)

    async def handle_lane_selection(self, interaction: discord.Interaction):
        # 버튼의 custom_id에서 라인 이름을 가져옴 (e.g., "lane_탑" -> "탑")
        button_label = interaction.data["custom_id"].split("_")[1]
        self.selections[interaction.user.id] = button_label
        await self.update_view_and_message(interaction)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, custom_id="start_button")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.danger, custom_id="cancel_button")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        embed = discord.Embed(title="🚫 모집 취소 🚫", description="호스트에 의해 모집이 취소되었습니다.", color=discord.Color.dark_red())
        await interaction.response.edit_message(embed=embed, view=None)

# --- 메인 Cog 클래스 ---
class RandomLaneCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        setup_database()

    def _get_or_create_user_stats(self, cursor: sqlite3.Cursor, user_id: int) -> tuple:
        cursor.execute("SELECT top, jungle, mid, bot, support, fixed FROM lane_stats WHERE user_id = ?", (user_id,))
        stats = cursor.fetchone()
        if stats:
            return stats
        else:
            cursor.execute("INSERT INTO lane_stats (user_id) VALUES (?)", (user_id,))
            return (0, 0, 0, 0, 0, 0)

    def _calculate_lane_weights(self, stats: tuple, available_lanes: list) -> dict:
        """사용자의 통계를 기반으로 가능한 라인들의 가중치를 계산합니다."""
        random_games = sum(stats[:5])
        # 가중치: (랜덤 게임 수 - 해당 라인 플레이 수) + 1. 적게 한 라인일수록 높은 가중치.
        weights = [(random_games - count) + 1 for count in stats[:5]] 
        return {lane: weights[LANE_NAMES.index(lane)] for lane in available_lanes}

    def _assign_lanes_final(self, selections: dict) -> dict:
        """선택사항을 바탕으로 최종 라인을 배정합니다."""
        final_assignments = {}
        # 1. 고정 포지션 우선 배정
        fixed_players = {uid: LANE_CHOICES[choice] for uid, choice in selections.items() if choice != "상관없음"}
        final_assignments.update(fixed_players)

        # 2. 남은 '상관없음' 플레이어와 가능한 라인 정리
        fill_player_ids = [uid for uid, choice in selections.items() if choice == "상관없음"]
        available_lanes = list(set(LANE_NAMES) - set(fixed_players.values()))
        random.shuffle(fill_player_ids)
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for user_id in fill_player_ids:
                if not available_lanes: break
                
                stats = self._get_or_create_user_stats(cursor, user_id)
                lane_weights = self._calculate_lane_weights(stats, available_lanes)
                
                if not lane_weights: break

                chosen_lane = random.choices(list(lane_weights.keys()), weights=list(lane_weights.values()), k=1)[0]
                final_assignments[user_id] = chosen_lane
                available_lanes.remove(chosen_lane)
        
        return final_assignments

    def _update_stats_after_assignment(self, selections: dict, final_assignments: dict):
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for user_id, lane in final_assignments.items():
                # '상관없음'을 선택한 유저는 랜덤 배정된 라인(lane)으로, 고정 선택 유저는 'fixed'로 기록
                lane_to_update = lane if selections[user_id] == "상관없음" else "fixed"
                
                # SQL injection을 방지하기 위해 컬럼 이름을 직접 검증. (중요)
                if lane_to_update not in LANE_NAMES + ["fixed"]: continue
                
                # f-string을 사용하지만, 위에서 안전하게 검증되었으므로 사용 가능
                sql = f"UPDATE lane_stats SET {lane_to_update} = {lane_to_update} + 1 WHERE user_id = ?"
                cursor.execute(sql, (user_id,))
            conn.commit()

    @commands.command(name='랜덤라인', help='5인 팀의 라인을 선택 또는 랜덤으로 정해줍니다.')
    async def random_lane(self, ctx: commands.Context):
        # 1단계: 모집
        recruitment_view = RecruitmentView(host=ctx.author)
        message = await ctx.send(embed=recruitment_view.create_recruitment_embed(), view=recruitment_view)
        
        if await recruitment_view.wait(): # True이면 타임아웃
            fail_embed = discord.Embed(title="😥 멤버 모집 실패 😥", description="아쉽게도 2분 안에 5명의 파티원이 모이지 않았어요.", color=discord.Color.dark_grey())
            await message.edit(embed=fail_embed, view=None)
            return

        if len(recruitment_view.participants) != 5: # 취소된 경우
            return

        # 2단계: 포지션 선택
        position_view = PositionSelectionView(host=ctx.author, participants=recruitment_view.participants)
        await message.edit(embed=position_view.create_selection_embed(), view=position_view)
        
        if await position_view.wait(): # True이면 타임아웃
            fail_embed = discord.Embed(title="😥 시간 초과 😥", description="시간 안에 포지션 선택이 완료되지 않아 취소되었습니다.", color=discord.Color.dark_grey())
            await message.edit(embed=fail_embed, view=None)
            return
            
        if len(position_view.selections) != 5: # 취소된 경우
            return

        # 3단계: 최종 결과 발표
        final_assignments = self._assign_lanes_final(position_view.selections)
        self._update_stats_after_assignment(position_view.selections, final_assignments)

        result_desc = []
        for user_id, lane in final_assignments.items():
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            emoji = LANE_DATA.get(lane, {}).get("emoji", "❔")
            result_desc.append(f"{emoji} **{lane.capitalize()}** : {user.mention}")
            
        result_embed = discord.Embed(title="🎉 포지션 분배 완료! 🎉", description="\n".join(result_desc), color=discord.Color.green())
        await message.edit(embed=result_embed, view=None)


    @commands.command(name='라인통계', help='자신의 라인별 플레이 통계를 원형 차트로 보여줍니다.')
    async def lane_stats(self, ctx):
        user = ctx.author
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            stats = self._get_or_create_user_stats(cursor, user.id)
            conn.commit() # _get_or_create_user_stats가 INSERT를 했을 수 있으므로 commit

        lane_counts = stats[0:5]
        fixed_plays = stats[5]
        random_plays = sum(lane_counts)
        total_games = random_plays + fixed_plays

        if total_games == 0:
            await ctx.send(f"{user.mention}님은 아직 플레이 기록이 없습니다. `!랜덤라인`을 통해 게임을 플레이해주세요!")
            return

        # --- 원형 차트 생성 ---
        labels = [LANE_DATA[name]['korean'] for name in LANE_NAMES]
        filtered_labels = [label for i, label in enumerate(labels) if lane_counts[i] > 0]
        filtered_counts = [count for count in lane_counts if count > 0]

        fig, ax = plt.subplots(figsize=(8, 6), facecolor='#D4D4D4')
        ax.set_facecolor("#D4D4D4")
        
        if random_plays > 0:
            text_props = {'fontsize': 14, 'color': 'white', 'fontweight': 'bold'}
            text_effects = [path_effects.withStroke(linewidth=3, foreground='black')]
            
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
        embed = discord.Embed(title=f"📊 {user.display_name}님의 플레이 통계", color=discord.Color.purple())
        embed.set_image(url="attachment://stats.png")

        dist_text = ""
        for i, label in enumerate(labels):
            percentage = (lane_counts[i] / random_plays) * 100 if random_plays > 0 else 0
            dist_text += f"{label}: {lane_counts[i]}회 ({percentage:.1f}%)\n"
        embed.add_field(name="📈 랜덤 라인 분포", value=dist_text, inline=True)

        summary_text = (f"﹒랜덤 플레이: {random_plays}회\n"
                        f"﹒고정 플레이: {fixed_plays}회\n"
                        f"**﹒총 플레이: {total_games}회**")
        embed.add_field(name="📋 플레이 요약", value=summary_text, inline=True)
        
        await ctx.send(file=file, embed=embed)

async def setup(bot):
    await bot.add_cog(RandomLaneCog(bot))