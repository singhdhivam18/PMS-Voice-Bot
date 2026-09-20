import logging

from app.config import config
from app.consumer import consume


logging.basicConfig(
    level=getattr(
        logging,
        config.LOG_LEVEL.upper(),
        logging.INFO,
    ),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main():
    logger = logging.getLogger("consumer.main")

    logger.info("Starting Maintenance Call Consumer Worker")

    consume()


if __name__ == "__main__":
    main()