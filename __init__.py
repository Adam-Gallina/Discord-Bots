from .examplecog import ExampleCog
from redbot.core import bot as Bot

def setup(bot:Bot):
    bot.add_cog(ExampleCog())