# cogs/admin_cog.py

import discord
from discord.ext import commands
import os
from app_config import app_config

def is_admin():
    async def predicate(ctx):
        return ctx.author.id == app_config.admin
    return commands.check(predicate)

#관리자 전용 기능들을 포함하는 Cog입니다.
class AdminCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='로드')
    @is_admin()
    async def load_cog(self, ctx, cog_name: str):
        try:
            await self.bot.load_extension(f'cogs.{cog_name}')
            await ctx.send(f'`{cog_name}` Cog가 성공적으로 로드되었습니다.')
        except Exception as e:
            await ctx.send(f'`{cog_name}` Cog 로드 중 오류가 발생했습니다: {e}')

    @commands.command(name='언로드')
    @is_admin()
    async def unload_cog(self, ctx, cog_name: str):
        try:
            await self.bot.unload_extension(f'cogs.{cog_name}')
            await ctx.send(f'`{cog_name}` Cog가 성공적으로 언로드되었습니다.')
        except Exception as e:
            await ctx.send(f'`{cog_name}` Cog 언로드 중 오류가 발생했습니다: {e}')

    @commands.command(name='리로드')
    @is_admin()
    async def reload_cog(self, ctx, cog_name: str):
        try:
            await self.bot.reload_extension(f'cogs.{cog_name}')
            await ctx.send(f'`{cog_name}` Cog가 성공적으로 리로드되었습니다.')
        except Exception as e:
            await ctx.send(f'`{cog_name}` Cog 리로드 중 오류가 발생했습니다: {e}')



    @commands.command(name='리스타트')
    @is_admin()
    async def restart_all_cogs(self, ctx):
        reloaded_cogs = []
        error_cogs = []
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                cog_name = filename[:-3]
                try:
                    await self.bot.reload_extension(f'cogs.{cog_name}')
                    reloaded_cogs.append(cog_name)
                except Exception as e:
                    error_cogs.append(f'{cog_name} ({e})')
        
        response = "Cog 리스타트 결과:\n"
        if reloaded_cogs:
            response += f"✅ **성공:** `{'`, `'.join(reloaded_cogs)}`\n"
        if error_cogs:
            response += f"❌ **실패:** `{'`, `'.join(error_cogs)}`"
            
        await ctx.send(response)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))