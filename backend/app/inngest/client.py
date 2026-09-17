import logging

import inngest

from app.core.config import settings

logger = logging.getLogger("inngest")

inngest_client = inngest.Inngest(
    app_id="smartticket",
    is_production=not settings.inngest_dev,
    event_key=settings.inngest_event_key or None,
    signing_key=settings.inngest_signing_key or None,
    api_base_url=settings.inngest_base_url if settings.inngest_dev else None,
    event_api_base_url=settings.inngest_base_url if settings.inngest_dev else None,
    logger=logger,
)
