from .skynetv2 import SkynetV2

async def setup(bot):
    """Setup function called when loading the cog."""
    cog = SkynetV2(bot)
    
    # Try to remove any existing 'ai' command first to prevent conflicts
    try:
        bot.tree.remove_command('ai')
    except Exception:
        # Command might not exist, that's fine
        pass
    
    await bot.add_cog(cog)

async def teardown(bot):
    """Teardown function called when unloading the cog."""
    # Additional cleanup if needed
    try:
        bot.tree.remove_command('ai')
    except Exception:
        pass
