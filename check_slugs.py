#!/usr/bin/env python
import os, sys
os.chdir('tabbycat')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
import django
django.setup()
from tournaments.models import Tournament
slugs = list(Tournament.objects.values_list('slug', flat=True))
print("ALL SLUGS:", slugs)
reserved = ['admin', 'jet', 'database', 'accounts', 'api', 'static', 'media']
conflicts = [s for s in slugs if s.lower() in reserved]
print("CONFLICTS:", conflicts)
