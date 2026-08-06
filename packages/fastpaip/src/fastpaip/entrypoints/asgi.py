"""ASGI entrypoint: configuration, and nothing else.

Everything here is a deployment decision — build the app, decide whether it
creates its own schema, set the log level. The logic being configured lives
elsewhere.
"""

import logging

from fastpaip.core.db import create_tables
from fastpaip.core.settings import get_settings
from fastpaip.views import create_app, lifespan_running

settings = get_settings()
logging.basicConfig(level=settings.log_level)

# Creating the schema is a development convenience and wrong for production: it
# adds missing tables and is silently insufficient once a column changes. See
# the migrations gap in fastpaip.core.db.
#
# It runs in the application's lifespan rather than here at import, so that
# importing this module does not connect to a database. See lifespan_running.
app = create_app(lifespan=lifespan_running(create_tables))

__all__ = ["app"]
