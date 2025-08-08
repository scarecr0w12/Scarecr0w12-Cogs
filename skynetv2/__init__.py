from .skynetv2 import SkynetV2

async def setup(bot):
    """Setup function called when loading the cog."""
    cog = SkynetV2(bot)
    await bot.add_cog(cog)
