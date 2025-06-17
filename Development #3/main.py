# main.py 

import discord
from discord.ext import commands

import os
import asyncio

from app_config import app_config 

class ConfitBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=app_config.prefixes,
            intents=discord.Intents.all()
        )

    async def setup_hook(self):
        print("Cogs를 로드합니다...")
        if not os.path.exists('./cogs'):
            print("cogs 폴더가 존재하지 않습니다.")
            print("------")
            return
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'{filename[:-3]} Cog가 로드되었습니다.')
                except Exception as e:
                    print(f'{filename[:-3]} Cog 로드 중 오류 발생: {e}')
        print("------")

    async def on_ready(self):
        print(f'{self.user.name} 봇이 성공적으로 로그인했습니다!')
        print(f'봇 ID: {self.user.id}')
        print('======')

if __name__ == '__main__':
    bot = ConfitBot()
    try:
        bot.run(app_config.token)
    except discord.errors.LoginFailure:
        print("에러: 유효하지 않은 토큰입니다. app_config.py 파일의 BOT_TOKEN을 확인해주세요.")