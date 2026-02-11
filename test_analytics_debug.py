#!/usr/bin/env python
"""Test analytics view on Heroku to find the actual error."""
import os, sys, traceback
from pathlib import Path

# Add tabbycat to path
tabbycat_dir = Path(__file__).resolve().parent / 'tabbycat'
if str(tabbycat_dir) not in sys.path:
    sys.path.insert(0, str(tabbycat_dir))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

import django
django.setup()

print("Django setup OK")

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore

User = get_user_model()
u = User.objects.filter(is_superuser=True).first()
print(f"User: {u}")

factory = RequestFactory()
request = factory.get('/analytics/')
request.user = u
request.session = SessionStore()

from analytics.views import DashboardView
view = DashboardView()
view.request = request
view.kwargs = {}
view.args = ()

print("\n--- Testing get_context_data ---")
try:
    ctx = view.get_context_data()
    print(f"SUCCESS! Context keys: {list(ctx.keys())}")
except Exception as e:
    print(f"ERROR in get_context_data: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n--- Testing template render ---")
try:
    from django.template.loader import get_template
    t = get_template('analytics/dashboard.html')
    print("Template loaded OK")
    result = t.render(ctx, request)
    print(f"Template rendered OK, length: {len(result)}")
except Exception as e:
    print(f"ERROR in template render: {type(e).__name__}: {e}")
    traceback.print_exc()
