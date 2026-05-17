import random
import time

from jobspy.linkedin import LinkedIn
from jobspy.model import DescriptionFormat, ScraperInput, Site

LINKEDIN_ID_PREFIX = "li-"


def build_scraper() -> LinkedIn:
    scraper = LinkedIn()
    scraper.scraper_input = ScraperInput(
        site_type=[Site.LINKEDIN],
        description_format=DescriptionFormat.MARKDOWN,
    )
    return scraper


def fetch_jd(scraper: LinkedIn, source_id: str) -> str | None:
    job_id = source_id.removeprefix(LINKEDIN_ID_PREFIX)
    details = scraper._get_job_details(job_id)
    return details.get("description") or None


def polite_sleep(scraper: LinkedIn) -> None:
    time.sleep(scraper.delay + random.uniform(0, scraper.band_delay))
