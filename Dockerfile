# QuestEd — single stage.
#
# The compiled stylesheet and the .mo translation catalogues are committed, so
# there is no Node build and no compilemessages step: the image only needs
# Python.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so edits to the app don't invalidate the install layer.
COPY quested/requirements.txt /app/quested/requirements.txt
RUN pip install -r /app/quested/requirements.txt

COPY . /app

WORKDIR /app/quested

# `settings.py` deliberately has no fallback for SECRET_KEY, so a missing key is
# a loud error rather than a silent insecure default. collectstatic still has to
# import settings at build time, hence a throwaway key that never leaves this
# layer — the real one arrives from the environment at run time.
RUN SECRET_KEY=build-only-throwaway \
    DEBUG=False \
    python manage.py collectstatic --noinput

# Runtime state lives on volumes; create the mount points before dropping root.
RUN useradd --create-home --uid 10001 quested \
    && mkdir -p /app/data /app/quested/media \
    && chown -R quested:quested /app/data /app/quested/media

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER quested

EXPOSE 8000

# Hits a real view, so the check fails if Django itself is broken and not just
# if the port is open. No curl in the slim image, so use Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/it/accounts/login/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "quested.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
