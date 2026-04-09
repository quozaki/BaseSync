import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TOKEN')

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='.', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f"BaseSync version: {os.getenv('BaseSync')}")


@bot.command()
async def ping(ctx):
    await ctx.send(f'Pong! {bot.latency*1000:.0f}ms')


bot.run(TOKEN)
