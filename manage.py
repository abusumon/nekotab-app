#!/usr/bin/env python
import os
import sys
from pathlib import Path

if __name__ == '__main__':
	# Ensure 'tabbycat' package apps (e.g., 'actionlog') are importable by short name
	project_root = Path(__file__).resolve().parent
	tabbycat_dir = project_root / 'tabbycat'
	if str(tabbycat_dir) not in sys.path:
		sys.path.insert(0, str(tabbycat_dir))

	# Use the package-qualified settings module when running from repo root
	os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tabbycat.settings')

	try:
		from django.core.management import execute_from_command_line
	except ImportError as exc:
		raise ImportError(
			"Couldn't import Django. Are you sure it's installed and "
			"available on your PYTHONPATH environment variable? Did you "
			"forget to activate a virtual environment?",
		) from exc

	execute_from_command_line(sys.argv)