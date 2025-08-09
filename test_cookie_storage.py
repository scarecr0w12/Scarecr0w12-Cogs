#!/usr/bin/env python3
"""Test exactly what EncryptedCookieStorage expects."""

import sys
from cryptography import fernet
from aiohttp_session.cookie_storage import EncryptedCookieStorage

# Generate a test key
key_bytes = fernet.Fernet.generate_key()  # This is bytes
key_string = key_bytes.decode()  # This is the base64 string

print(f"Key bytes type: {type(key_bytes)}, len: {len(key_bytes)}")
print(f"Key string type: {type(key_string)}, len: {len(key_string)}")
print(f"Key bytes: {key_bytes}")
print(f"Key string: {key_string}")

# Test what formats work with EncryptedCookieStorage
test_cases = [
    ("Raw bytes from Fernet.generate_key()", key_bytes),
    ("String decoded from bytes", key_string),
    ("String encoded to UTF-8 bytes", key_string.encode('utf-8')),
    ("String encoded to ASCII bytes", key_string.encode('ascii')),
]

for desc, key in test_cases:
    try:
        storage = EncryptedCookieStorage(key, max_age=86400)
        print(f"✅ {desc}: SUCCESS")
    except Exception as e:
        print(f"❌ {desc}: FAILED - {e}")

print("\n" + "="*60)
print("SUMMARY: Testing what EncryptedCookieStorage accepts")
print("="*60)
