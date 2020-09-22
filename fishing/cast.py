from discord import Embed
from random import choices, randint

class FishData:
    def __init__(self, name, minSize, maxSize, baseValue, school, rarity, image):
        self.name = name
        self.minSize = minSize
        self.maxSize = maxSize
        self.baseValue = baseValue
        self.school = school
        self.rarity = rarity
        self.image:str = image

    def ToFishCatch(self, value):
        size = round(float(randint(self.minSize * 100, self.maxSize * 100) / 100), 2)
        newFish = { 'name': self.name,
                    'school': self.school,
                    'rarity':self.rarity,
                    'size': size,
                    'value': (self.baseValue + value * size) }
        return newFish

def FishToEmbed(embed, name, size, value):
    return embed.add_field(name=f'{name} ({round(size, 2)} inches)', value=value, inline=False)
