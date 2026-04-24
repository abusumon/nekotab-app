# Docker file lists all the commands needed to setup a fresh linux instance to
# run the application specified. docker-compose does not use this.

# Grab a python image
FROM python:3.11
SHELL ["/bin/bash", "--login", "-c"]

# Just needed for all things python (note this is setting an env variable)
ENV PYTHONUNBUFFERED 1
# Needed for correct settings input
ENV IN_DOCKER 1

# Setup Node/NPM
RUN apt-get update && apt-get install -y --no-install-recommends curl nginx && rm -rf /var/lib/apt/lists/*

# Install nvm — NVM_DIR must be set as ENV so all subsequent RUN layers can source it
ENV NVM_DIR=/root/.nvm
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Copy all our files into the baseimage and cd to that directory
WORKDIR /tcd
COPY . /tcd/

# Install Node (reads version from .nvmrc) and set as default
# Explicit `. $NVM_DIR/nvm.sh` is more reliable than relying on bash login-shell profile
RUN . $NVM_DIR/nvm.sh && nvm install && nvm use && nvm alias default $(nvm current)

# Set git to use HTTPS (SSH is often blocked by firewalls)
RUN git config --global url."https://".insteadOf git://

# Install Python dependencies
RUN pip install pipenv
RUN pipenv install --system --deploy

# Install Node dependencies and build frontend assets
RUN . $NVM_DIR/nvm.sh && npm ci
RUN . $NVM_DIR/nvm.sh && npm run build

# Collect static files (manage.py is no longer excluded in .dockerignore)
RUN python ./manage.py collectstatic --noinput -v 0

# Fix line endings and set executable bit on the DO entrypoint script
# (file is committed from Windows so may have CRLF)
RUN sed -i 's/\r//' /tcd/bin/do-web-start.sh && chmod +x /tcd/bin/do-web-start.sh

