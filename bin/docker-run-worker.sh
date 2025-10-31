#!/usr/bin/env bash
#   Shorthand to run django worker in docker

cd NekoTab

# Run worker
python ./manage.py runworker notifications adjallocation venues

