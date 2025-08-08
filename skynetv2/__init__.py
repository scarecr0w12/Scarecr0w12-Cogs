from .skynetv2 import SkynetV2

async def setup(bot):
    """Setup function called when loading the cog."""
    # Try to remove any existing commands first to prevent conflicts
    for command_name in ['ai', 'skynet', 'skynetv2']:
        try:
            bot.tree.remove_command(command_name)
        except Exception:
            # Command might not exist, that's fine
            pass
    
    cog = SkynetV2(bot)
    await bot.add_cog(cog)

async def teardown(bot):
    """Teardown function called when unloading the cog."""
    # Clean up slash commands
    for command_name in ['ai', 'skynet', 'skynetv2']:
        try:
            bot.tree.remove_command(command_name)
        except Exception:
            pass
