"""ASGI entrypoint: configuration, and nothing else.

Everything here is a deployment decision — build the app and set the log level.
The logic being configured lives elsewhere.

Note what this does *not* do: create tables. The schema belongs to Alembic, and
a deployment runs ``alembic upgrade head`` before starting this process. An
application that builds its own schema on boot will, the first time a model
changes, start successfully against a database that is missing a column and fail
later at the query — which is a worse failure than refusing to start.
"""

import logging

from fastpaip.core.settings import get_settings
from fastpaip.views import create_app

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = create_app()

__all__ = ["app"]
