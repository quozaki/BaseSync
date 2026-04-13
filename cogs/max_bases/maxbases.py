from discord.ext import commands

class MaxBases(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Add commands here

async def setup(bot):
    await bot.add_cog(MaxBases(bot))