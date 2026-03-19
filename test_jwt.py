"""Quick test: sign a JWT with Django's SECRET_KEY, decode with nekospeech's jwt_secret_key."""
import os, sys, time
sys.path.insert(0, 'nekospeech')

# Simulate Django side
django_key = os.environ.get('DJANGO_SECRET_KEY', '')
print(f"Django SECRET_KEY len={len(django_key)} repr={repr(django_key[:15])}...")

# Simulate nekospeech side
from nekospeech.config import settings as ns_settings
print(f"Nekospeech jwt_secret_key len={len(ns_settings.jwt_secret_key)} repr={repr(ns_settings.jwt_secret_key[:15])}...")
print(f"Keys match: {django_key == ns_settings.jwt_secret_key}")

from jose import jwt
payload = {"user_id": 1, "role": "director", "iat": int(time.time()), "exp": int(time.time()) + 3600}
token = jwt.encode(payload, django_key, algorithm="HS256")
print(f"Token: {token[:50]}...")

try:
    decoded = jwt.decode(token, ns_settings.jwt_secret_key, algorithms=["HS256"])
    print(f"Decode SUCCESS: {decoded}")
except Exception as e:
    print(f"Decode FAILED: {type(e).__name__}: {e}")
