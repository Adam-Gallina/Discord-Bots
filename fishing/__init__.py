from .fishing import Fishing
from redbot.core import bot

def setup(botInstance:bot):
    f = Fishing()
    f.LoadFish('fish_rarities.json')
    botInstance.add_cog(f)