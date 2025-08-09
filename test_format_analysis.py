#!/usr/bin/env python3
"""Test what format might work for EncryptedCookieStorage based on docs and similar libraries."""

import sys
import base64
from cryptography import fernet

# Generate test key
key_bytes = fernet.Fernet.generate_key()  # Returns bytes
key_string = key_bytes.decode()           # Base64 string

print(f"Generated Fernet key (bytes): {key_bytes}")
print(f"Generated Fernet key (string): {key_string}")
print(f"Key bytes length: {len(key_bytes)}")
print(f"Key string length: {len(key_string)}")

# According to aiohttp-session docs, EncryptedCookieStorage expects:
# "secret_key should be 32 url-safe base64-encoded bytes"

print("\n--- Expected format analysis ---")
print("aiohttp-session docs say: 'secret_key should be 32 url-safe base64-encoded bytes'")
print("This means it wants the RAW 32 BYTES, not the base64 string!")

# The 32 bytes
raw_bytes = base64.urlsafe_b64decode(key_string)
print(f"Raw decoded bytes: {raw_bytes}")
print(f"Raw bytes length: {len(raw_bytes)}")

# Test if our current approach matches this
current_approach = key_string.encode('utf-8')  # What we're doing now
print(f"Current approach (string.encode('utf-8')): {current_approach}")
print(f"Current approach length: {len(current_approach)}")

print("\n--- Comparison ---")
print(f"Expected (raw 32 bytes): {len(raw_bytes)} bytes")
print(f"Current (encoded string): {len(current_approach)} bytes")
print(f"Match? {len(raw_bytes) == 32 and len(current_approach) == 44}")

print("\n--- Solution ---")
print("EncryptedCookieStorage likely wants the 32 raw bytes, not the 44-char base64 string!")
print("We should use base64.urlsafe_b64decode(key_string) instead of key_string.encode('utf-8')")
