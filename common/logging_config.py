import logging
import sys

from pythonjsonlogger import jsonlogger

from common.config import Settings


def configure_logging(settings: Settings, tool_name: str = "qa-suite") -> None:
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_json:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()
    root.addHandler(handler)

    # Inject tool name into every log record
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = old_factory(*args, **kwargs)
        record.tool = tool_name
        return record

    logging.setLogRecordFactory(record_factory)
