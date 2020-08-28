from discord import Embed

class Merchant:
    def __init__(self, name:str, quality_type:str, qualities:[str], sell_mod:float):
        self.name = name
        self.quality_type = quality_type
        self.qualities = qualities
        self.sell_mod = sell_mod

    def ToEmbed(self):
        description = f'**Looking for fish with {self.quality_type}:**'
        for i in self.qualities:
            description += '\n  ' + i
        description += '\n\n' + f'*Will purchase for {self.sell_mod}x the value*'

        embed = Embed(title=f'{self.name}\'s shop', description=description)
        return embed

    def CheckFish(self, fish:{}):
        return fish[self.quality_type] in self.qualities

