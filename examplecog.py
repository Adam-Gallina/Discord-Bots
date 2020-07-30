from redbot.core import commands

class ExampleCog(commands.Cog):
    @commands.command()
    async def poop(self, ctx):
        await ctx.send('poop ' * 10)