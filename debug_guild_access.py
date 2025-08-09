#!/usr/bin/env python3
"""Debug guild access for SkynetV2 web interface"""

import asyncio
import sys

async def debug_guild_access():
    """Debug guild access by simulating bot.get_guild() call"""
    
    target_guild_id = 600375939951493100
    print(f"Debugging access to guild ID: {target_guild_id}")
    print(f"Guild ID type: {type(target_guild_id)}")
    
    # Simulate what the bot might see
    # This is just for debugging the ID format
    print(f"String version: '{str(target_guild_id)}'")
    print(f"Int version: {int(target_guild_id)}")
    
    # Check if this is a valid snowflake ID
    import time
    discord_epoch = 1420070400000  # January 1, 2015
    timestamp = ((target_guild_id >> 22) + discord_epoch) / 1000
    created_time = time.ctime(timestamp)
    print(f"Guild created approximately: {created_time}")
    
    print("\nThis script can't access Discord directly, but check:")
    print("1. Is the bot actually in that guild?")
    print("2. Check bot console logs when trying to toggle")
    print("3. Verify the guild ID is correct")
    print(f"4. Try this Discord command: [p]ai channel status (in guild {target_guild_id})")

if __name__ == "__main__":
    asyncio.run(debug_guild_access())
