import asyncio
from redbot.core import commands, Config, checks
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.menus import start_adding_reactions, menu, DEFAULT_CONTROLS
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core import bank
from discord import utils, Member, Embed
import json
from time import time
from random import randint, choices, sample, choice

from .cast import FishToEmbed, FishData
from .shopping import Merchant

bucket_image = 'https://art.pixilart.com/6a832d621d201ea.png'
POOL_CHANNEL = 'pool'
SHOP_CHANNEL = 'shop'
FISH_RARITIES = ['common', 'rare', 'abyssal']
RARITY_DESCRIPTIONS = {'common':'You feel a tugging at your line',
                       'rare':'You feel a large jolt on your line',
                       'abyssal':'An overbearing force from deep below suddenly appears'}
RARITY_VALUES = {'common':1,
                 'rare':4,
                 'abyssal':10}
FISH_WEIGHTS = [50, 7, 1]

class Fishing(commands.Cog):
    fishing_rarities:{str:[FishData]} = {}
    merchant_qualities = {}
    curr_merchants = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SEA_BASS = None

        self.config = Config.get_conf(self, identifier=11235813)
        default_member = {
            'times_fished': 0,
            'bucket': [],
            'next_cast': 0,
            'bucket_size': 50,
            'mawiam_mode': False,
            'bryan_mode': True
        }
        default_guild = {
            'channels': {},
            'settings': { 'pool_category': 'fishing',
                          'fishing_delay': 15,
                          'bucket_display_length': 5,
                          'max_fishing_length': 60,
                          'min_fishing_wait': 3,
                          'max_fishing_wait': 9,
                          'min_merchants': 2,
                          'max_merchants': 5,
                          'max_merchant_qualities': 7},
            'value_modifiers': { 'common': 1,
                                 'rare': 1,
                                 'abyssal': 1,
                                 'non_shop_sell': 0.75},
        }
        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)

    def LoadFish(self, pool_file):
        fish_names = []
        fish_classes = []

        fish_data_fp = bundled_data_path(self) / pool_file
        with fish_data_fp.open() as f:
            fish_data = json.load(f)

            for i in FISH_RARITIES:
                new_fishies = []

                for fish_name in fish_data[i].keys():
                    curr_fish = fish_data[i][fish_name]
                    new_fishies.append(FishData(fish_name, curr_fish['min_size'], curr_fish['max_size'], curr_fish['value'], curr_fish['class'], i, curr_fish['image']))

                    if fish_name == 'Sea Bass':
                        self.SEA_BASS = new_fishies[-1]

                    #For merchants:
                    fish_names.append(fish_name)
                    if not curr_fish['class'] in fish_classes:
                        fish_classes.append(curr_fish['class'])

                self.fishing_rarities.update({ i:new_fishies })

        self.merchant_qualities = { 'name': fish_names,
                                    'class': fish_classes,
                                    'rarity': FISH_RARITIES }
    #region Helper functions
    async def AddSpecializedChannel(self, guild, channel_id:int, channel_type:str):
        channels:{} = await self.config.guild(guild).channels()
        channels.update({ str(channel_id):channel_type })
        await self.config.guild(guild).channels.set(channels)

    async def IsSpecialized(self, guild, channel_id:int, channel_type:str = ''):
        if channel_type == '':
            return await self.GetChannelType(guild, channel_id) != 'none'
        return await self.GetChannelType(guild, channel_id) == channel_type

    async def GetChannelType(self, guild, channel_id:int):
        return (await self.config.guild(guild).channels()).get(str(channel_id), 'none')

    async def AddFish(self, member, fish):
        all_fish = await self.config.member(member).bucket()
        if len(all_fish) >= await self.config.member(member).bucket_size():
            return False
        all_fish.append(fish)
        await self.config.member(member).bucket.set(all_fish)
        return True

    async def GetSetting(self, guild, setting):
        return (await self.config.guild(guild).settings())[setting]

    async def GetModifier(self, guild, modifier):
        return (await self.config.guild(guild).value_modifiers())[modifier]
    #endregion

    #region Specialized Channel Moderation
    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def new(self, ctx, channel_name, channel_type):
        channel_check = utils.get(ctx.guild.channels, name=channel_name)
        if channel_check:
            await ctx.send(f'<!{channel_check.id}> already exists! Use `add <channel type>` within the channel to make it a {channel_type}')
            return

        msg = await ctx.send(f'Are you sure you want to create a new {channel_type} called {channel_name}?')

        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=15)
        except asyncio.TimeoutError:
            await ctx.send(f'Channel ({channel_type}) creation request timed out')
            return

        if pred.result is True:
            category = utils.get(ctx.guild.categories, name=await self.GetSetting(ctx.guild, 'pool_category'))
            if category is None:
                category = await ctx.guild.create_category(await self.GetSetting(ctx.guild, 'pool_category'))
            newChannel = await ctx.guild.create_text_channel(channel_name, category=category)
            await self.AddSpecializedChannel(ctx.guild, newChannel.id, channel_type)

            await ctx.send(f'<#{newChannel.id}> created')
        else:
            await ctx.send(f'{channel_type} creation request cancelled')

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def add(self, ctx, t):
        if not t in [POOL_CHANNEL, SHOP_CHANNEL]:
            await ctx.send(f'{t} is not a valid channel type\n_Channel types:_\npool\nshop')

        channel_type = await self.GetChannelType(ctx.guild, ctx.channel.id)
        if channel_type == 'none':
            await self.AddSpecializedChannel(ctx.guild, ctx.channel.id, t)
            await ctx.send(f'<#{ctx.channel.id}> is now a {t}!')
        else:
            await ctx.send(f'<#{ctx.channel.id}> is already a {channel_type}!')

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def rem(self, ctx):
        if await self.IsSpecialized(ctx.guild, ctx.channel.id):
            channels = await self.config.guild(ctx.guild).channels()
            t = channels.pop(str(ctx.channel.id))
            await self.config.guild(ctx.guild).channels.set(channels)
            await ctx.send(f'<#{ctx.channel.id}> is no longer a {t}')
        else:
            await ctx.send(f'<#{ctx.channel.id}> was never specialized!')

    @commands.command()
    async def checktype(self, ctx):
        t = await self.GetChannelType(ctx.guild, ctx.channel.id)
        if t == 'none':
            await ctx.send(
                f'<#{ctx.channel.id}> is a normal channel (use `add <channel type>` to make this a specialized channel)')
        else:
            await ctx.send(f'<#{ctx.channel.id}> is a {t}')
    #endregion

    #region Fishing
    @commands.command()
    async def bucket(self, ctx, member: Member = None):
        await self.bucketsort(ctx, '', '', member)

    @commands.command()
    async def bucketsort(self, ctx, sort_type:str, sort_parameter:str, member:Member = None):
        if not sort_type in ['name', 'class', 'rarity', '']:
            await ctx.send(f'{sort_type} must be one of the following:\n```name\nclass\nrarity```')
            return

        if member is None:
            member = ctx.message.author

        embeds = []
        currfish = await self.config.member(member).bucket()
        display_length = await self.GetSetting(ctx.guild, 'bucket_display_length')
        newEmbed = Embed(title=f'{member.display_name}\'s Bucket' + (' (' + sort_parameter + ' only)' if not sort_type == '' else '') + ':')
        newEmbed.set_thumbnail(url=bucket_image)
        for i in range(len(currfish)):
            if i != 0 and i % display_length == 0:
                embeds.append(newEmbed)

                if i == len(currfish) - 1:
                    break

                newEmbed = Embed(title=f'{member.display_name}\'s Bucket:')
                newEmbed.set_thumbnail(url=bucket_image)

            if sort_type == '' or currfish[i][sort_type] == sort_parameter:
                newEmbed = FishToEmbed(newEmbed, currfish[i]['name'], currfish[i]['size'], currfish[i]['value'])
        else:
            embeds.append(newEmbed)

        await menu(ctx, embeds, DEFAULT_CONTROLS, timeout=45)

    @commands.command()
    async def cast(self, ctx, bait_type:str = ''):
        if not await self.IsSpecialized(ctx.guild, ctx.channel.id, POOL_CHANNEL):
            return

        profile = self.config.member(ctx.message.author)
        if await profile.next_cast() > int(time()):
            await ctx.send(f'Your fishing rod is still recharging ({int(await profile.next_cast())} seconds remaining...)')

        await profile.times_fished.set(await profile.times_fished() + 1)

        #baitPower = 0
        #if bait_type != '':
        #if not fishingBait.get(baitType):
        #   await ctx.send(f'{baitType} is not valid bait')
        #   return
        #baitPower = fishingBait[baitType]

        embed = Embed(title=f'{ctx.message.author.display_name} cast their rod into the shimmering waves at {ctx.channel}', color=0x7300ff)
        embed.set_footer(text='Not even a nibble yet...')
        msg = await ctx.send(embed=embed)
        start_adding_reactions(msg, ['🎣'])

        pred = ReactionPredicate.with_emojis(['🎣'], msg, ctx.author)
        time_left = await self.GetSetting(ctx.guild, 'max_fishing_length')
        min_pause = await self.GetSetting(ctx.guild, 'min_fishing_wait')
        max_pause = await self.GetSetting(ctx.guild, 'max_fishing_wait')
        curr_fish = None
        rarity = None
        while time_left >= 0:
            try:
                timer = time_left if time_left < max_pause else randint(min_pause, max_pause)
                time_left -= timer
                await ctx.bot.wait_for('reaction_add', check=pred, timeout=timer)
            except asyncio.TimeoutError:
                if curr_fish is None:
                    rarity = choices(FISH_RARITIES, FISH_WEIGHTS)[0]
                    rarity_list = self.fishing_rarities.get(rarity)
                    curr_fish = rarity_list[randint(0, len(rarity_list) - 1)] if not await profile.bryan_mode() else self.SEA_BASS
                    embed.set_footer(text=RARITY_DESCRIPTIONS[rarity])
                else:
                    curr_fish = None
                    embed.set_footer(text='The rod drifts in the water')
                await msg.edit(embed=embed)

            if pred.result == 0:
                break
        if curr_fish is None or time_left <= 0:
            embed.set_footer(text='You feel a twist as the line snaps :(')
            await msg.edit(embed=embed)
            await msg.clear_reactions()
        else:
            new_fish = curr_fish.ToFishCatch(RARITY_VALUES[rarity])
            embed.set_footer(text=f'You pulled a {new_fish["name"]} ({new_fish["size"]} inches) out of the water!')
            await msg.edit(embed=embed)
            await msg.clear_reactions()

            start_adding_reactions(msg, ['🥤', '🐟'])
            if not await profile.mawiam_mode():
                await profile.nextcast.set(time() + await self.GetSetting(ctx.guild, 'fishing_delay'))

            pred = ReactionPredicate.with_emojis(['🥤', '🐟'], msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=15)
            except asyncio.TimeoutError:
                if await self.AddFish(ctx.message.author, new_fish):
                    embed.set_footer(text=f'Timed out, {new_fish["name"]} was added to your bucket')
                else:
                    embed.set_footer(text=f'Timed out and your bucket was full, so {new_fish["name"]} was released :(')
                await msg.edit(embed=embed)
                await msg.clear_reactions()
                return

            if pred.result == 0:
                if await self.AddFish(ctx.message.author, new_fish):
                    embed.set_footer(text=f'{new_fish["name"]} was added to your bucket!')
                else:
                    embed.set_footer(text=f'Your bucket was full, so you had to release {new_fish["name"]} :(')
            else:
                embed.set_footer(text=f'You let {new_fish["name"]} swim away...')
            await msg.edit(embed=embed)
            await msg.clear_reactions()
    #endregion

    #region Shopping
    @commands.command()
    @checks.admin()
    async def refreshshops(self, ctx):
        if not await self.IsSpecialized(ctx.guild, ctx.channel.id, SHOP_CHANNEL):
            await ctx.send('Cannot refresh the shops here\nUse `add shop` to turn this channel into a shop')
            return

        if not self.curr_merchants.get(ctx.guild.id):
            self.curr_merchants.update({ ctx.guild.id : [] })
        else:
            self.curr_merchants[ctx.guild.id] = []
        for i in range(randint(await self.GetSetting(ctx.guild, 'min_merchants'), await self.GetSetting(ctx.guild, 'max_merchants'))):
            rand_quality_name = choice(list(self.merchant_qualities.keys()))
            rand_quality = self.merchant_qualities[rand_quality_name]

            max_qualities = await self.GetSetting(ctx.guild, 'max_merchant_qualities')
            max_qualities = max_qualities if len(rand_quality) / 2 > max_qualities else int(len(rand_quality) / 2)

            new_merchant = Merchant('We need names', rand_quality_name, sample(rand_quality, randint(1, max_qualities)), 1)
            embed = new_merchant.ToEmbed()
            await ctx.send(embed=embed)
            self.curr_merchants[ctx.guild.id].append(new_merchant)

    async def CheckMerchants(self, guild, fish):
        mod = await self.GetModifier(guild, 'non_shop_sell')
        for i in self.curr_merchants[guild.id]:
            if i.CheckFish(fish) and i.sell_mod > mod:
                mod = i.sell_mod
        return mod

    @commands.command()
    async def sellall(self, ctx, fish_type:str='', fish_quality:str=''):
        if not fish_type in ['name', 'class', 'rarity', '']:
            await ctx.send(f'{fish_type} must be one of the following:\n```name\nclass\nrarity```')
            return

        all_fish = await self.config.member(ctx.message.author).bucket()
        new_fish = []
        sell_fish = []
        msg = ''
        total = 0
        for i in all_fish:
            if fish_type == '' or i[fish_type] == fish_quality:
                sell_fish.append(i)

                name, mod = await self.CheckMerchants(ctx.guild, i)
                i["value"] = int(i["value"] * mod * await self.GetModifier(ctx.guild, i['rarity']))
                total += i["value"]
                msg += f'{i["name"]}{" " * (12 - len(i["name"]))}{i["value"]} {await bank.get_currency_name(ctx.guild)} ({mod}x)\n'
            else:
                new_fish.append(i)

        msg = await ctx.send(f'Are you sure you want to sell:\n```{msg}```for {total}')

        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=10)
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            return

        if pred.result is True:
            #increase players money by total
            await self.config.member(ctx.message.author).bucket.set(new_fish)
            await msg.edit(content=f'{len(sell_fish)} fish sold for {total} {await bank.get_currency_name(ctx.guild)}')
            await bank.deposit_credits(ctx.message.author, total)
        else:
            await msg.edit(content='Sale cancelled')

        await msg.clear_reactions()
    #endregion

    #region Settings
    @commands.command()
    @checks.admin()
    async def changesetting(self, ctx, setting, new_value: int):
        settings = await self.config.guild(ctx.guild).settings()

        if not settings.get(setting):
            await ctx.send(f'{setting} is not a valid setting\n```Valid settings:\nfishing_delay: Length (seconds) between casts from a user\nbucket_display_length: Amount of fish to display per page with /bucket```')
            return

        settings[setting] = new_value
        await self.config.guild(ctx.guild).settings.set(settings)
        await ctx.send(f'{setting} updated')

    @commands.command()
    @checks.admin()
    async def changemodifier(self, ctx, mod:str, new_value:int):
        mods = await self.config.guild(ctx.guild).value_modifiers()

        if not mods.get(mod):
            await ctx.send(f'{mod} is not a valid modifier\n```Available modifiers:\nFish values:\ncommon\nrare\nabyssal```')
            return

        mods[mod] = new_value
        await self.config.guild(ctx.guild).value_modifiers().set(mods)
        await ctx.send(f'{mod} modifier was updated')

    @commands.command()
    @checks.admin()
    async def mawiammode(self, ctx, member: Member, enabled: bool):
        await self.config.member(member).mawiam_mode.set(enabled)
        await ctx.send(f'{member.mention} has mawiam mode set to {enabled}')

    @commands.command()
    @checks.admin()
    async def bryanmode(self, ctx, member: Member, enabled: bool):
        await self.config.member(member).bryan_mode.set(enabled)
        await ctx.send(f'{member.mention} has bryan mode set to {enabled}')
    #endregion

