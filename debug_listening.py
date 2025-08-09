#!/usr/bin/env python3
"""Debug script to test SkynetV2 listening configuration"""

import asyncio
import json

def debug_listening_config():
    """Test function to simulate the listening logic"""
    
    # Simulate different config scenarios
    scenarios = [
        {
            "name": "Channel enabled with mode 'all'",
            "channel_listening": {
                "123456789": {
                    "enabled": True,
                    "mode": "all"
                }
            },
            "global_listening": {"enabled": False, "mode": "mention", "keywords": []},
            "channel_id": "123456789",
            "expected_trigger": True
        },
        {
            "name": "Channel enabled with mode 'mention'",
            "channel_listening": {
                "123456789": {
                    "enabled": True,
                    "mode": "mention"
                }
            },
            "global_listening": {"enabled": False, "mode": "mention", "keywords": []},
            "channel_id": "123456789", 
            "expected_trigger": False  # Would need mention to trigger
        },
        {
            "name": "No channel config, global disabled",
            "channel_listening": {},
            "global_listening": {"enabled": False, "mode": "mention", "keywords": []},
            "channel_id": "123456789",
            "expected_trigger": False
        },
        {
            "name": "No channel config, global enabled with 'all'",
            "channel_listening": {},
            "global_listening": {"enabled": True, "mode": "all", "keywords": []},
            "channel_id": "123456789",
            "expected_trigger": True
        }
    ]
    
    for scenario in scenarios:
        print(f"\n=== {scenario['name']} ===")
        
        # Simulate the listener logic
        channel_listening_config = scenario["channel_listening"]
        channel_id = scenario["channel_id"]
        global_listening = scenario["global_listening"]
        
        print(f"Channel listening config: {channel_listening_config}")
        print(f"Channel ID: {channel_id}")
        print(f"Global listening config: {global_listening}")
        
        # Channel-specific override
        if channel_id in channel_listening_config:
            channel_config = channel_listening_config[channel_id]
            print(f"Found channel-specific config: {channel_config}")
            if not channel_config.get("enabled", False):
                print(f"Channel listening disabled")
                triggered = False
            else:
                listening = channel_config
                mode = listening.get("mode", "mention")
                print(f"Using channel config with mode: {mode}")
                triggered = (mode == "all")  # Simplified for test
        else:
            # Fall back to global guild listening config
            listening = global_listening
            print(f"Using global listening config: {listening}")
            if not listening or not listening.get("enabled", False):
                print(f"Global listening disabled or not configured")
                triggered = False
            else:
                mode = listening.get("mode", "mention")
                print(f"Using global config with mode: {mode}")
                triggered = (mode == "all")  # Simplified for test
        
        print(f"Expected: {scenario['expected_trigger']}, Got: {triggered}")
        if triggered == scenario['expected_trigger']:
            print("✅ PASS")
        else:
            print("❌ FAIL")

if __name__ == "__main__":
    debug_listening_config()
