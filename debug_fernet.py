#!/usr/bin/env python3
"""
Debug the exact Fernet key issue step by step.
"""

from cryptography import fernet
import base64

def debug_key_format():
    """Debug exactly what format EncryptedCookieStorage expects."""
    print("=== Debugging Fernet Key Format Issue ===")
    
    # Generate a test key like our code does
    key_string = fernet.Fernet.generate_key().decode()
    print(f"1. Generated key string: {repr(key_string)}")
    print(f"   Length: {len(key_string)}")
    print(f"   Type: {type(key_string)}")
    
    # Test different ways of handling it
    print("\n--- Testing different key formats ---")
    
    # Method 1: Direct Fernet creation (this should work)
    try:
        f1 = fernet.Fernet(key_string)
        print("✅ Method 1: fernet.Fernet(string) - SUCCESS")
    except Exception as e:
        print(f"❌ Method 1: fernet.Fernet(string) - FAILED: {e}")
    
    # Method 2: Fernet with string encoded as bytes
    try:
        f2 = fernet.Fernet(key_string.encode('utf-8'))
        print("✅ Method 2: fernet.Fernet(string.encode('utf-8')) - SUCCESS")
    except Exception as e:
        print(f"❌ Method 2: fernet.Fernet(string.encode('utf-8')) - FAILED: {e}")
    
    # Method 3: Check what EncryptedCookieStorage actually expects
    print("\n--- Testing what EncryptedCookieStorage wants ---")
    
    # The error suggests it wants base64-encoded bytes, let's see...
    key_bytes_utf8 = key_string.encode('utf-8')
    print(f"Key as UTF-8 bytes: {repr(key_bytes_utf8)}")
    print(f"Length: {len(key_bytes_utf8)}")
    
    # Test if these bytes decode properly as base64
    try:
        decoded = base64.urlsafe_b64decode(key_bytes_utf8)
        print(f"✅ Base64 decode successful: {len(decoded)} bytes")
        if len(decoded) == 32:
            print("✅ Decoded to exactly 32 bytes (correct for Fernet)")
        else:
            print(f"❌ Decoded to {len(decoded)} bytes, expected 32")
    except Exception as e:
        print(f"❌ Base64 decode failed: {e}")
    
    # Test if the original key is actually already bytes
    key_bytes_direct = fernet.Fernet.generate_key()
    print(f"\nDirect generated key: {repr(key_bytes_direct)}")
    print(f"Length: {len(key_bytes_direct)}")
    print(f"Type: {type(key_bytes_direct)}")
    
    try:
        f3 = fernet.Fernet(key_bytes_direct)
        print("✅ Direct bytes work with Fernet")
    except Exception as e:
        print(f"❌ Direct bytes failed with Fernet: {e}")

if __name__ == "__main__":
    debug_key_format()
