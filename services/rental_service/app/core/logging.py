import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(service_name: str, log_dir: str = "logs", level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(log_dir) / f"{service_name}.log"

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError as exc:
        # Bind-mounted host logs may be root-owned; keep console logging.
        root.warning("File logging disabled for %s: %s", log_path, exc)
        return
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
