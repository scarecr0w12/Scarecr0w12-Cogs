async def setup(bot):
    """Setup function called when loading the cog."""
    from .skynetv2 import SkynetV2  # local import to avoid eager deps during test collection
    cog = SkynetV2(bot)
    await bot.add_cog(cog)
