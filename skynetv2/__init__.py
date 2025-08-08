from .skynetv2 import SkynetV2

async def setup(bot):
    await bot.add_cog(SkynetV2(bot))
