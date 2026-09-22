"""Run the housekeeping: `python -m app.jobs.purge` once, or `--every SECONDS` to keep running
(the compose `purge` service does the latter)."""

import argparse
import asyncio
import logging

from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.services.purge import purge
from app.storage import get_storage

logger = logging.getLogger(__name__)


async def run_once() -> None:
    async with get_sessionmaker()() as session:
        await purge(session, get_storage())


async def main(every: int | None) -> None:
    while True:
        try:
            await run_once()
        except Exception:
            logger.exception("purge run failed")
            if every is None:
                raise
        if every is None:
            return
        await asyncio.sleep(every)


if __name__ == "__main__":
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--every", type=int, default=None, help="repeat every N seconds")
    asyncio.run(main(parser.parse_args().every))
