# Docker file lists all the commands needed to setup a fresh linux instance to
# run the application specified. docker-compose does not use this.

# Grab a python image
FROM python:3.11
SHELL ["/bin/bash", "--login", "-c"]

# Just needed for all things python (note this is setting an env variable)
ENV PYTHONUNBUFFERED=1
# Needed for correct settings input
ENV IN_DOCKER=1

# Pin pipenv to avoid lock-hash drift between local and CI/deploy environments.
ARG PIPENV_VERSION=2026.6.1

# Install Node.js 18 LTS via NodeSource — no nvm, no shell-sourcing hacks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl nginx && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Copy all our files into the baseimage and cd to that directory
WORKDIR /tcd
COPY . /tcd/

# Set git to use HTTPS (SSH is often blocked by firewalls)
RUN git config --global url."https://".insteadOf git://

# Install Python dependencies
RUN pip install "pipenv==${PIPENV_VERSION}"
RUN pipenv install --system --deploy

# Install Node dependencies and build frontend assets
RUN npm ci
RUN npm run build

# Collect static files during image build. Use a non-sensitive temporary key
# for this step only; runtime DJANGO_SECRET_KEY still comes from deployment env.
RUN DJANGO_SECRET_KEY=build-time-placeholder-key python ./manage.py collectstatic --noinput --ignore='*.bak' -v 0

# Strip CRLF from ALL shell scripts and config files baked into the image.
# Files are committed from Windows and may have \r\n line endings which break
# bash on Linux.  gunicorn config is Python so Python handles CRLF, but we
# normalise it here too for safety.
RUN find /tcd/bin -name "*.sh" -exec sed -i 's/\r//' {} \; && \
    find /tcd/bin -name "*.sh" -exec chmod +x {} \; && \
    sed -i 's/\r//' /tcd/config/gunicorn-do.conf
