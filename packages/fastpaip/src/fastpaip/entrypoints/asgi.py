"""ASGI entrypoint: configuration, and nothing else.

Everything here is a deployment decision — build the app, ensure the schema
exists, set the log level. The logic being configured lives elsewhere.
"""

import logging

from fastpaip.core.db import create_tables
from fastpaip.core.settings import get_settings
from fastpaip.views import create_app

settings = get_settings()
logging.basicConfig(level=settings.log_level)

# Development convenience, and wrong for production: this creates missing tables
# and is silently insufficient once a column changes. See the migrations gap in
# fastpaip.core.db.
create_tables()

app = create_app()

__all__ = ["app"]
