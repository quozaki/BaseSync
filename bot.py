import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.calc import calc_max_bases_supported

load_dotenv()
TOKEN = os.getenv('TOKEN')

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='.', intents=intents)

def load_cogs():
    for root, dirs, files in os.walk('cogs'):
        for file in files:
            if file.endswith('.py'):
                # Construct the module path
                rel_path = os.path.relpath(root, '.')
                module_path = rel_path.replace(os.sep, '.') + '.' + file[:-3]
                try:
                    bot.load_extension(module_path)
                    print(f'Loaded cog: {module_path}')
                except Exception as e:
                    print(f'Failed to load cog {module_path}: {e}')

load_cogs()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f"BaseSync version: {os.getenv('BaseSync')}")


@bot.command()
async def ping(ctx):
    await ctx.send(f'Pong! {bot.latency*1000:.0f}ms')


@bot.command()
async def test(ctx, unit, bases: int):
    result = calc_max_bases_supported(unit, bases)
    await ctx.send(f"Result: {result}")


bot.run(TOKEN)
