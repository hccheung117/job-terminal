"""Patch python-jobspy 1.1.82 so LinkedIn date_posted is populated.

Upstream adds a fallback for the new `job-search-card__listdate--new` class
(https://github.com/speedyapply/JobSpy/pull/343) but it is unreleased.
Remove this module once a release > 1.1.82 ships the fix.
"""
from jobspy.linkedin import LinkedIn

_orig_process_job = LinkedIn._process_job


def _patched_process_job(self, job_card, job_id, full_descr):
    metadata_card = job_card.find("div", class_="base-search-card__metadata")
    if metadata_card and not metadata_card.find(
        "time", class_="job-search-card__listdate"
    ):
        tag = metadata_card.find("time", class_="job-search-card__listdate--new")
        if tag:
            tag["class"] = ["job-search-card__listdate"]
    return _orig_process_job(self, job_card, job_id, full_descr)


LinkedIn._process_job = _patched_process_job
