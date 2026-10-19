import logging


def configure_logging(level: str) -> None:
    """Configure process logging without emitting configuration values."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
