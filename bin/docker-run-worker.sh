#!/usr/bin/env bash
#   Shorthand to run django worker in docker

# Run worker
python manage.py runworker notifications adjallocation venues

