import logging
import sys

from loguru import logger

from bacteria.observability.context import get_context


def _context_patcher(record: dict) -> None:
    # Inject trace_id, job_id, etc. into every log line automatically.
    # Called by loguru before writing each record — no need to pass context manually.
    record["extra"].update(get_context())


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    # Must be called once at startup (before anything logs) from setup_observability().
    # Replaces Python's default logging with loguru and unifies all log output.

    # Remove loguru's default stderr handler so we control the sink entirely.
    logger.remove()

    if fmt == "json":
        # Production: one JSON object per line so log aggregators (Datadog, Loki, etc.)
        # can parse fields like trace_id and job_id without regex.
        logger.add(
            sys.stdout,
            level=level,
            serialize=True,
            format="{message}",
            backtrace=False,
            diagnose=False,
        )
    else:
        # Development: colored human-readable output.
        # {extra} at the end is where context fields (trace_id, job_id, ...) appear.
        # backtrace + diagnose print local variable values on exceptions — no debugger needed.
        logger.add(
            sys.stdout,
            level=level,
            colorize=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan> - "
                "<level>{message}</level>"
                "{extra}"
            ),
            backtrace=True,
            diagnose=True,
        )

    logger.configure(patcher=_context_patcher)

    # Bridge stdlib logging → loguru so SQLAlchemy, uvicorn, etc. go through loguru.
    # _InterceptHandler re-emits stdlib records through loguru, preserving the original
    # file/line by walking up the call stack to skip the logging internals (depth).
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in logging.root.manager.loggerDict:
        # Clear any handlers third-party libraries registered on their own loggers
        # so their output bubbles up to _InterceptHandler instead of being handled twice.
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk up the call stack past logging internals so loguru reports the
        # original caller's file and line, not this intercept file.
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
