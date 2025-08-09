#!/usr/bin/env python3
"""
Test the corrected session key format for EncryptedCookieStorage.
This simulates our fix without needing aiohttp_session installed.
"""

import base64
from cryptography import fernet

def test_session_key_fix():
    """Test the corrected session key handling."""
    print("=== Testing Session Key Fix ===")
    
    # Step 1: Generate a key like our code does
    key_bytes = fernet.Fernet.generate_key()  # bytes
    key_string = key_bytes.decode()           # base64 string
    
    print(f"Generated key bytes: {key_bytes}")
    print(f"Generated key string: {key_string}")
    print(f"Key string length: {len(key_string)}")
    
    # Step 2: Test our OLD approach (what was causing the error)
    old_approach = key_string.encode('utf-8')
    print(f"\nOLD approach (encode to UTF-8): {old_approach}")
    print(f"OLD approach length: {len(old_approach)} bytes")
    
    # Step 3: Test our NEW approach (what should work)
    new_approach = base64.urlsafe_b64decode(key_string)
    print(f"NEW approach (decode from base64): {new_approach}")
    print(f"NEW approach length: {len(new_approach)} bytes")
    
    # Step 4: Verify the new approach gives us the expected 32 bytes
    if len(new_approach) == 32:
        print("✅ NEW approach produces exactly 32 bytes (correct for EncryptedCookieStorage)")
    else:
        print(f"❌ NEW approach produces {len(new_approach)} bytes, expected 32")
    
    # Step 5: Verify the key still works with Fernet
    try:
        # Test both the original formats work with Fernet
        f1 = fernet.Fernet(key_bytes)  # Direct bytes
        f2 = fernet.Fernet(key_string)  # Base64 string
        print("✅ Key still works with Fernet in both formats")
        
        # Test encryption/decryption works
        test_data = b"Hello, SkynetV2!"
        encrypted = f1.encrypt(test_data)
        decrypted = f2.decrypt(encrypted)
        if decrypted == test_data:
            print("✅ Encryption/decryption works correctly")
        else:
            print("❌ Encryption/decryption failed")
            
    except Exception as e:
        print(f"❌ Fernet operation failed: {e}")

if __name__ == "__main__":
    test_session_key_fix()
