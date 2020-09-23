import asyncio
from redbot.core import commands, Config, checks, events
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
schools_image = 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Lutjanus_kasmira_school.jpg/540px-Lutjanus_kasmira_school.jpg'
POOL_CHANNEL = 'pool'
SHOP_CHANNEL = 'shop'
FISH_RARITIES = ['common', 'rare', 'abyssal']
RARITY_DESCRIPTIONS = {'common': 'You feel a tugging at your line',
                       'rare': 'You feel a large jolt on your line',
                       'abyssal': 'An overbearing force from deep below suddenly appears'}
RARITY_VALUES = {'common': 1,
                 'rare': 4,
                 'abyssal': 10}
FISH_WEIGHTS = [35, 11, 1]
fishing_bait = { 'worm': 0,
                 'fly': 1,
                 'chum' : 2,
                 'enchanted nightcrawler': 5,
                 'master bait': 10 }
bait_prices = { 'worm': 1,
                'fly': 4,
                'chum': 7,
                'enchanted nightcrawler': 12,
                'master bait': 25 }

class Fishing(commands.Cog):
    fishing_rarities:{str:[FishData]} = {}
    merchant_qualities = {}
    curr_merchants = {}
    merchant_names = []
    merchant_wait_times = {}
    fish_schools:{str:[str]} = {}

    #Message formatting
    longestFishName = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SEA_BASS = None

        self.config = Config.get_conf(self, identifier=11235813)
        default_member = {
            'times_fished': 0,
            'bait': { 'worm': 0,
                      'fly': 0,
                      'chum' : 0,
                      'enchanted_nightcrawler': 0,
                      'master_bait': 0 },
            'bucket': [],
            'schools': {},
            'next_cast': 0,
            'rod_level': 0,
            'currently_fishing': False,
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
                          'min_merchant_wait': 2,
                          'max_merchant_wait': 6,
                          'max_merchant_qualities': 7,
                          'bait_recovery_chance': .1,
                          'bulk_minimum': 10 },
            'value_modifiers': { 'common': 1,
                                 'rare': 1,
                                 'abyssal': 1,
                                 'non_shop_sell': 0.75,
                                 'bait_price': 350,
                                 'bulk_purchase_mod': .1,
                                 'school_complete_mod': .25},
        }
        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)

    #Reads the information found in data/fish_rarities.json and store it in self.fishing_rarities
    def LoadFish(self, pool_file):
        fish_names = []
        schools = []

        fish_data_fp = bundled_data_path(self) / pool_file
        with fish_data_fp.open() as f:
            fish_data = json.load(f)

            for i in FISH_RARITIES:
                new_fishies = []

                for fish_name in fish_data[i].keys():
                    curr_fish = fish_data[i][fish_name]
                    new_fishies.append(FishData(fish_name, curr_fish['min_size'], curr_fish['max_size'], curr_fish['value'], curr_fish['school'], i, curr_fish['image']))

                    if fish_name == 'Sea Bass':
                        self.SEA_BASS = new_fishies[-1]

                    #For merchants:
                    fish_names.append(fish_name)
                    if not curr_fish['school'] in schools:
                        schools.append(curr_fish['school'])
                        self.fish_schools.update({curr_fish['school'] : [fish_name] })
                    else:
                        self.fish_schools[curr_fish['school']].append(fish_name)

                    #For formatting
                    if len(fish_name) > self.longestFishName:
                        self.longestFishName = len(fish_name)

                self.fishing_rarities.update({ i:new_fishies })

        self.longestFishName += 1
        self.merchant_qualities = { 'name': fish_names,
                                    'school': schools,
                                    'rarity': FISH_RARITIES }

    #Reads the names in data/merchant_names.txt and stores it in self.merchant_names
    def LoadMerchants(self, merchant_data_path):
        with open(bundled_data_path(self) / merchant_data_path, 'r') as f:
            self.merchant_names = f.read().split('\n')

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
        await self.UpdateSchools(member, fish)
        return True

    async def UpdateSchools(self, member, fish):
        member_schools = await self.config.member(member).schools()

        if not fish['school'] in member_schools:
            member_schools.update({ fish['school']:{} })

        if not fish['name'] in member_schools[fish['school']]:
            member_schools[fish['school']].update({ fish['name']:fish['size'] })
        elif fish['size'] > member_schools[fish['school']][fish['name']]:
            member_schools[fish['school']][fish['name']] = fish['size']

        await self.config.member(member).schools.set(member_schools)

    async def GetSetting(self, guild, setting):
        return (await self.config.guild(guild).settings())[setting]

    async def GetModifier(self, guild, modifier):
        return (await self.config.guild(guild).value_modifiers())[modifier]
    #endregion

    @commands.Cog.listener()
    async def on_message_without_command(self, message):
        if message.author.bot:
            return

        # Check shop generation
        if await self.IsSpecialized(message.guild, message.channel.id, SHOP_CHANNEL):
            if self.merchant_wait_times.get(message.guild.id, 0) <= time():
                await self.RefreshMerchants(message.guild, message.channel)

    #region Specialized Channel Moderation
    @commands.group()
    async def managechannels(self, ctx:commands.Context):
        """Contains commands to register/deregister channels as specialized"""

    @managechannels.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def register(self, ctx:commands.Context, channel_type):
        """Designates a channel to be either a pool or a shop, and allow users to fish or sell within them"""

        if not channel_type in [POOL_CHANNEL, SHOP_CHANNEL]:
            await ctx.send(f'{channel_type} is not a valid channel type\n_Channel types:_\npool\nshop')

        channel_type = await self.GetChannelType(ctx.guild, ctx.channel.id)
        if channel_type == 'none':
            await self.AddSpecializedChannel(ctx.guild, ctx.channel.id, channel_type)
            await ctx.send(f'<#{ctx.channel.id}> is now a {channel_type}!')
        else:
            await ctx.send(f'<#{ctx.channel.id}> is already a {channel_type}!')

    @managechannels.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def deregister(self, ctx:commands.Context):
        """Removes a specialization from a channel"""

        if await self.IsSpecialized(ctx.guild, ctx.channel.id):
            channels = await self.config.guild(ctx.guild).channels()
            t = channels.pop(str(ctx.channel.id))
            await self.config.guild(ctx.guild).channels.set(channels)
            await ctx.send(f'<#{ctx.channel.id}> is no longer a {t}')
        else:
            await ctx.send(f'<#{ctx.channel.id}> was never specialized!')

    @managechannels.command()
    async def checktype(self, ctx:commands.Context):
        """Displays if a channel has been registered as a type or is a normal channel"""

        t = await self.GetChannelType(ctx.guild, ctx.channel.id)
        if t == 'none':
            await ctx.send(
                f'<#{ctx.channel.id}> is a normal channel (use `register <channel type>` to make this a specialized channel)')
        else:
            await ctx.send(f'<#{ctx.channel.id}> is a {t}')
    #endregion

    #region Fishing
    @commands.command()
    async def bucket(self, ctx:commands.Context, member: Member = None):
        """Show the fish a specific member has caught"""

        await self.bucketsort(ctx, '', '', member)

    @commands.command()
    async def bucketsort(self, ctx:commands.Context, sort_type:str, sort_parameter:str, member:Member = None):
        """Shows the fish of a specific category (name, school, or rarity) a specific member has caught"""

        if not sort_type in ['name', 'school', 'rarity', '']:
            await ctx.send(f'{sort_type} must be one of the following:\n```name\nschool\nrarity```')
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

    #Checks a given bait_type to be valid/owned by the user
    #Calculates the modified_fish_weights for use in catching a fish of a randomized type
    async def startfishing(self, ctx:commands.Context, profile, bait_type):
        if fishing_bait.get(bait_type) is None:
            await ctx.send(f'{bait_type} is not valid bait')
            return
        elif (await profile.bait()).get(bait_type) <= 0:
            await ctx.send(f'You\'re all out of {bait_type}. Buy more in the store with `bait <bait_type> <quantity>`')
            return
        baitPower = fishing_bait[bait_type]

        if (await profile.next_cast()) > int(time()):
            await ctx.send(f'Your fishing rod is still recharging ({int(await profile.next_cast())} seconds remaining...)')
            return
        elif await profile.currently_fishing():
            await ctx.send('Your rod is already in the water silly')
            return

        await profile.times_fished.set(await profile.times_fished() + 1)

        modified_fish_weights = [FISH_WEIGHTS[0],
                                 FISH_WEIGHTS[1] + baitPower + await profile.rod_level() * await self.GetModifier(ctx.guild, 'rod_rare'),
                                 FISH_WEIGHTS[2] + baitPower + await profile.rod_level() * await self.GetModifier(ctx.guild, 'rod_abyssal')]
        return modified_fish_weights

    @commands.command(aliases=['qcast', 'qc'])
    async def quickcast(self, ctx:commands.Context, bait_type:str):
        """Rolls for a fish - similar to cast, but you do not get to choose the fish to reel in, instead instantly rolling and choosing to keep/release a fish

         - Must be used in a channel registered as a pool"""

        if not await self.IsSpecialized(ctx.guild, ctx.channel.id, POOL_CHANNEL):
            return
        profile = self.config.member(ctx.message.author)

        await profile.currently_fishing.set(True)
        modified_fish_weights = await self.startfishing(ctx, profile, bait_type)

        rarity = choices(FISH_RARITIES, modified_fish_weights)[0]
        rarity_list = self.fishing_rarities.get(rarity)
        curr_fish = rarity_list[randint(0, len(rarity_list) - 1)] if not await profile.bryan_mode() else self.SEA_BASS
        new_fish = curr_fish.ToFishCatch(RARITY_VALUES[rarity])

        embed = Embed(title=f'{ctx.message.author.display_name} cast their rod into the shimmering waves at {ctx.channel}', color=0x7300ff)
        embed.set_footer(text=f'You pulled a {new_fish["name"]} ({new_fish["size"]} inches) out of the water!\nDo you want to keep or release?')
        embed.set_thumbnail(url=curr_fish.image)
        msg = await ctx.send(embed=embed)
        start_adding_reactions(msg, ['🥤', '🐟'])

        pred = ReactionPredicate.with_emojis(['🥤', '🐟'], msg, ctx.author)
        try:
            await ctx.bot.wait_for('reaction_add', check=pred, timeout=15)
        except asyncio.TimeoutError:
            pred.result = 0

        if pred.result == 0:
            if await self.AddFish(ctx.message.author, new_fish):
                embed.set_footer(text=f'{new_fish["name"]} was added to your bucket!')
            else:
                embed.set_footer(text=f'Your bucket was full, so you had to release {new_fish["name"]} :(')
        else:
            embed.set_footer(text=f'You let {new_fish["name"]} swim away...')
        await msg.edit(embed=embed)
        await msg.clear_reactions()

        user_bait = await profile.bait()
        user_bait[bait_type] -= 1
        await profile.bait.set(user_bait)

        await profile.currently_fishing.set(False)
        #if not await profile.mawiam_mode():
        #await profile.nextcast.set(time() + await self.GetSetting(ctx.guild, 'fishing_delay'))

        await self.CheckSchools(ctx)

    @commands.command()
    async def cast(self, ctx:commands.Context, bait_type:str):
        """Rolls for a fish
          Fish will periodically bite the pole, at which point the message can be reacted to to catch the fish
          After reeling in the rod, you will have the option to keep or release the fish

         - Must be used in a channel registered as a pool"""

        if not await self.IsSpecialized(ctx.guild, ctx.channel.id, POOL_CHANNEL):
            return
        profile = self.config.member(ctx.message.author)

        await profile.currently_fishing.set(True)
        modified_fish_weights = await self.startfishing(ctx, profile, bait_type)

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
                    rarity = choices(FISH_RARITIES, modified_fish_weights)[0]
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
            embed.set_footer(text=f'You pulled a {new_fish["name"]} ({new_fish["size"]} inches) out of the water!\nDo you want to keep or release?')
            embed.set_thumbnail(url=curr_fish.image)
            await msg.edit(embed=embed)
            await msg.clear_reactions()

            start_adding_reactions(msg, ['🥤', '🐟'])

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
            else:
                if pred.result == 0:
                    if await self.AddFish(ctx.message.author, new_fish):
                        embed.set_footer(text=f'{new_fish["name"]} was added to your bucket!')
                    else:
                        embed.set_footer(text=f'Your bucket was full, so you had to release {new_fish["name"]} :(')
                else:
                    embed.set_footer(text=f'You let {new_fish["name"]} swim away...')
                await msg.edit(embed=embed)
                await msg.clear_reactions()

        if randint(0, 100) < 100 * await self.GetSetting(ctx.guild, 'bait_recovery_chance'):
            await ctx.send(f'Your {bait_type} is still on the end of the rod! (+1 {bait_type})')
        else:
            user_bait = await profile.bait()
            user_bait[bait_type] -= 1
            await profile.bait.set(user_bait)

        await profile.currently_fishing.set(False)
        #if not await profile.mawiam_mode():
        #await profile.nextcast.set(time() + await self.GetSetting(ctx.guild, 'fishing_delay'))

        await self.CheckSchools(ctx)

    @commands.command()
    async def bait(self, ctx:commands.Context):
        """Displays all of the bait in your inventory"""

        bait = ''
        member_bait = await self.config.member(ctx.message.author).bait()
        for i in member_bait.keys():
            if not member_bait[i] == 0:
                bait += f'{i}{" " * (25 - len(i))}{member_bait[i]}\n'
        await ctx.send(f'You have:\n```{bait[:-1]}```')
    #endregion

    #region Shopping
    @commands.command()
    @checks.admin()
    async def forceshopreset(self, ctx:commands.Context):
        """Allows an admin to skip the merchant cooldown and refresh the current merchants

         - Must be used in a channel registered as a shop"""

        if not await self.IsSpecialized(ctx.guild, ctx.channel.id, SHOP_CHANNEL):
            await ctx.send('Cannot refresh the shops here\nUse `add shop` to turn this channel into a shop')
            return

        await self.RefreshMerchants(ctx.guild, ctx.channel)

    async def RefreshMerchants(self, guild, channel):
        if not self.curr_merchants.get(guild.id):
            self.curr_merchants.update({ guild.id : [] })
            self.merchant_wait_times.update({ guild.id : 0 })
        else:
            self.curr_merchants[guild.id] = []
        min_wait = await self.GetSetting(guild, 'min_merchant_wait')
        max_wait = await self.GetSetting(guild, 'max_merchant_wait')
        self.merchant_wait_times[guild.id] = time() + randint(min_wait, max_wait) * 60 * 60

        #for i in range(randint(await self.GetSetting(ctx.guild, 'min_merchants'), await self.GetSetting(ctx.guild, 'max_merchants'))):
        rand_quality_name = choice(list(self.merchant_qualities.keys()))
        rand_quality = self.merchant_qualities[rand_quality_name]

        max_qualities = await self.GetSetting(guild, 'max_merchant_qualities')
        max_qualities = max_qualities if len(rand_quality) / 2 > max_qualities else int(len(rand_quality) / 2)

        rand_mod = float(randint(0, 30) / 10)
        if rand_mod == 0:
            rand_mod = 5
        elif rand_mod <= 1.5:
            rand_mod = 1

        new_merchant = Merchant(choice(self.merchant_names), rand_quality_name, sample(rand_quality, randint(1, max_qualities)), rand_mod)
        embed = new_merchant.ToEmbed()
        await channel.send(embed=embed)
        self.curr_merchants[guild.id].append(new_merchant)

    async def CheckMerchants(self, guild, fish):
        mod = await self.GetModifier(guild, 'non_shop_sell')
        if self.curr_merchants.get(guild.id):
            for i in self.curr_merchants[guild.id]:
                if i.CheckFish(fish) and i.sell_mod > mod:
                    mod = i.sell_mod
        return mod

    @commands.command()
    async def sell(self, ctx:commands.Context, name, size):
        """Sell one fish in your inventory chosen by a specified name and size

         - Prices affected by rarity modifiers"""

        await self.sellall(ctx, 'specific', f'{name} {size}')

    @commands.command()
    async def sellall(self, ctx:commands.Context, fish_type:str='', fish_quality:str=''):
        """Sell all of the fish in your bucket

         - Fish will automatically be sold to valid merchants
         - Can filter by categories (name, school, or rarity)
         - Sale prices are increased for fish from a school you've completed
         - Prices affected by rarity modifiers and school_complete_mod"""

        if not fish_type in ['specific', 'name', 'school', 'rarity', '']:
            await ctx.send(f'{fish_type} must be one of the following:\n```name\nschool\nrarity```')
            return

        all_fish = await self.config.member(ctx.message.author).bucket()
        new_fish = []
        sell_fish = []
        msg = ''
        total = 0
        for i in all_fish:
            i.update({'specific': f'{i["name"]} {i["size"]}'})
            if fish_type == '' or i[fish_type] == fish_quality:
                sell_fish.append(i)

                mod = await self.CheckMerchants(ctx.guild, i)
                if await self.CompletedSchool(ctx.message.author, i['school']):
                    mod += await self.GetModifier(ctx.guild, 'school_complete_mod')

                i["value"] = int(i["value"] * mod * await self.GetModifier(ctx.guild, i['rarity']))
                total += i["value"]
                msg += f'{i["name"]}{" " * (self.longestFishName - len(i["name"]))}{i["value"]} {await bank.get_currency_name(ctx.guild)} ({mod}x)\n'
            else:
                new_fish.append(i)

        msg = await ctx.send(f'Are you sure you want to sell:\n```{msg}```for {total} {await bank.get_currency_name(ctx.guild)}')

        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=20)
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            await msg.edit(content='Sale timed out')
            return

        if pred.result is True:
            await self.config.member(ctx.message.author).bucket.set(new_fish)
            await msg.edit(content=f'{len(sell_fish)} fish sold for {total} {await bank.get_currency_name(ctx.guild)}')
            await bank.deposit_credits(ctx.message.author, total)
        else:
            await msg.edit(content='Sale cancelled')

        await msg.clear_reactions()

    @commands.command()
    async def buybait(self, ctx:commands.Context, quantity:int, *bait_type:str):
        """Purchase bait to use with cast

         - prices affected by bait_price_mod and bulk_purchase_mod"""

        if not await self.IsSpecialized(ctx.guild, ctx.channel.id, SHOP_CHANNEL):
            await ctx.send('Cannot buy bait here\nUse `add shop` to turn this channel into a shop')
            return

        bait_type = ' '.join(bait_type)
        if not bait_type in fishing_bait:
            await ctx.send(f'{bait_type} is not a valid form of bait')

        bulk_mod = await self.GetModifier(ctx.guild, 'bulk_purchase_mod')
        bulk_requirement = await self.GetSetting(ctx.guild, 'bulk_minimum')
        total = int(bait_prices[bait_type] * quantity * await self.GetModifier(ctx.guild, "bait_price") * (1 if quantity < bulk_requirement else 1 - bulk_mod))

        if not bank.can_spend(ctx.message.author, total):
            await ctx.send(f'You don\'t have enough {await bank.get_currency_name(ctx.guild)}')
            return

        msg = await ctx.send(f'Are you sure you want to buy {bait_type} x{quantity} ({total} {await bank.get_currency_name(ctx.guild)})'
                             + (f'\n*-{100 * bulk_mod}% for buying in bulk*' if quantity >= bulk_requirement else ''))

        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=15)
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            return

        if pred.result is True:
            member_bait = await self.config.member(ctx.message.author).bait()
            member_bait[bait_type] += quantity
            await self.config.member(ctx.message.author).bait.set(member_bait)
            await msg.edit(content=f'{quantity} {bait_type} bought for {total} {await bank.get_currency_name(ctx.guild)}')
            await bank.withdraw_credits(ctx.message.author, total)
        else:
            await msg.edit(content='Sale cancelled')

        await msg.clear_reactions()
    #endregion

    #region Schools
    @commands.command()
    async def schools(self, ctx:commands.Context, member:Member = None):
        """Display your completion percentage of every school
        (use the school command to get more detailed information about a specific school)"""

        if member is None:
            member = ctx.message.author

        embeds = []
        member_schools = await self.config.member(member).schools()
        print(member_schools)
        display_length = await self.GetSetting(ctx.guild, 'bucket_display_length')
        keys = list(self.fish_schools.keys())

        newEmbed = Embed(title=f'{member.display_name}\'s Schools')
        newEmbed.set_thumbnail(url=schools_image)
        for i in range(len(keys)):
            if i != 0 and i % display_length == 0:
                embeds.append(newEmbed)

                if i == len(keys) - 1:
                    break

                newEmbed = Embed(title=f'{member.display_name}\'s Schools')
                newEmbed.set_thumbnail(url=schools_image)

            percent_completed = int(len(member_schools.get(keys[i], {})) / len(self.fish_schools[keys[i]]) * 100)
            newEmbed.add_field(name=keys[i], value=f'{percent_completed}%', inline=False)
        else:
            embeds.append(newEmbed)

        await menu(ctx, embeds, DEFAULT_CONTROLS, timeout=45)

    @commands.command()
    async def school(self, ctx:commands.Context, *school_name):
        """Display all of your obtained fish in a specific school"""

        school_name = ' '.join(school_name)
        if not school_name in list(self.fish_schools.keys()):
            await ctx.send(f'{school_name} is not a valid school')
            return

        curr_school = self.fish_schools[school_name]
        member_school = (await self.config.member(ctx.message.author).schools()).get(school_name, {})
        description = ''
        for i in curr_school:
            description += (f'{i}: {member_school[i]} inches' if i in member_school else '???') + '\n'
        embed = Embed(title=school_name, description=description[:-1])
        embed.set_thumbnail(url=schools_image)
        await ctx.send(embed=embed)

    async def CheckSchools(self, ctx:commands.Context):
        total_complete = 0
        for i in self.fish_schools.keys():
            if await self.CompletedSchool(ctx.message.author, i):
                total_complete += 1
        percent_complete = total_complete / len(self.fish_schools)
        level = int(percent_complete / .25)

        if await self.config.member(ctx.message.author).rod_level() < level:
            await self.config.member(ctx.message.author).rod_level.set(level)
            await ctx.send(f'You have completed {int(percent_complete * 100)}% of schools and unlocked rod level {level}!')

    async def CompletedSchool(self, member, school:str):
        member_schools = await self.config.member(member).schools()
        return len(self.fish_schools[school]) == len(member_schools.get(school, {}))
    #endregion

    #region Settings
    @commands.group()
    async def fishingsettings(self, ctx:commands.Context):
        """Modify various settings used by fishing"""

    @fishingsettings.command()
    @checks.admin()
    async def changesetting(self, ctx:commands.Context, setting, new_value: int):
        """Change values for timers and similar settings used by the cog

         - bucket_display_length: The number of fish to display per page when using bucket commands
         - max_fishing_length: The maximum amount of time a cast can last (seconds)
         - min_fishing_wait: The minimum amount of time for a cast to cycle between a bite and none (seconds)
         - max_fishing_wait: The maximum amount of time for a cast to cycle between a bite and none (seconds)
         - min_merchant_wait: The minimum random amount of time before a new merchant appears (hours)
         - max_merchant_wait: The maximum random amount of time before a new merchant appears (hours)
         - max_merchant_qualities: The maximum amount of specific fish types a merchant can look for
         - bait_recovery_chance: The chance for bait to be recovered after fishing
         - bulk_minimum: The minimum amount of bait to be bought to recieve a bulk discount"""

        settings = await self.config.guild(ctx.guild).settings()

        if not settings.get(setting):
            await ctx.send(f'{setting} is not a valid setting\n```Valid settings:\nfishing_delay: Length (seconds) between casts from a user\nbucket_display_length: Amount of fish to display per page with /bucket```')
            return

        settings[setting] = new_value
        await self.config.guild(ctx.guild).settings.set(settings)
        await ctx.send(f'{setting} updated')

    @fishingsettings.command(name="changemodifier")
    @checks.admin()
    async def changemodifier(self, ctx:commands.Context, mod:str, new_value:int):
        """Set modifiers for prices within the cog

         - common: The price modifier for common fish
         - rare: The price modifier for rare fish
         - abyssal: The price modifier for abyssal fish
         - non_shop_sell: The modifier for selling fish to the basic shop
         - bait_price: The modifier for buying bait
         - bulk_purchase_mod: The discount for buying bait in bulk (decimal percentage e.g. 0.1 for 10% off)
         - school_complete_mod: The increased sell price for selling a fish in a school you've completed (decimal percentage)"""

        mods = await self.config.guild(ctx.guild).value_modifiers()

        if not mods.get(mod):
            await ctx.send(f'{mod} is not a valid modifier\n```Available modifiers:\nFish values:\ncommon\nrare\nabyssal```')
            return

        mods[mod] = new_value
        await self.config.guild(ctx.guild).value_modifiers().set(mods)
        await ctx.send(f'{mod} modifier was updated')

    #@fishingsettings.command()
    #@checks.admin()
    #async def mawiammode(self, ctx:commands.Context, member: Member, enabled: bool):
    #    """Remove fishing cooldowns for a user (currently not in use)"""
#
    #    await self.config.member(member).mawiam_mode.set(enabled)
    #    await ctx.send(f'{member.mention} has mawiam mode set to {enabled}')

    @fishingsettings.command()
    @checks.admin()
    async def bryanmode(self, ctx:commands.Context, member: Member, enabled: bool):
        """Make a profile catch exclusively Sea Bass"""

        await self.config.member(member).bryan_mode.set(enabled)
        await ctx.send(f'{member.mention} has bryan mode set to {enabled}')

    @fishingsettings.command()
    @checks.admin()
    async def resettimer(self, ctx:commands.Context, member: Member = None):
        """If the cog gets shut down in the middle of a cast a user can get locked out of fishing, this fixes it"""

        await self.config.member(member if not member == None else ctx.message.author).currently_fishing.set(False)
        await ctx.send('Fishing cooldown reset')
    #endregion

    #delete me
    #@commands.command()
    #async def add(self, ctx:commands.Context, numb:int):
    #    await bank.deposit_credits(ctx.message.author, numb)
#
    @commands.command()
    async def addfish(self, ctx:commands.Context, *fish_name):
        fish_name = ' '.join(fish_name)
        for rarity in self.fishing_rarities:
            for fish in self.fishing_rarities[rarity]:
                if fish.name == fish_name:
                    await self.AddFish(ctx.message.author, fish.ToFishCatch(1))
                    await ctx.send(f'Added {fish_name}')
                    return
        await ctx.send(f'Could not find {fish_name}')