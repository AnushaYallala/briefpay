"""Submissions and their automatic checks (SPEC 7.3, 6.1). Flushes only; the caller owns the transaction.

A submission is one attempt (max 3) by the contract's freelancer while the project is IN_PROGRESS. Creating it moves the
project to VERIFYING and queues AUTO_CHECKS. The job runs the default checks plus each criterion's hint through `AutoChecker`
and saves one `auto_checks` row per check. Questions, evidence and judging are later increments (T-33, T-34): the submission
waits in QUESTIONING.
"""
import re
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AutoCheck, BRD, Contract, Evidence, Job, Project, ProjectMember, Submission, VerificationQuestion
from app.services import contract_service, jobs
from app.services.autochecks import SHA, AutoChecker, CheckResult, parse_repo
from app.services.safe_fetch import SafeFetcher
from app.services.state_machines import ProjectService

MAX_ATTEMPTS = 3
ACTIVE_STATES = ("SUBMITTED", "AUTO_CHECKING", "QUESTIONING", "EVIDENCE_RECEIVED", "JUDGING")
MAX_CHECKS = 60
MAX_NOTES = 2000


class SubmissionError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- how the job gets its checker (tests install a fake internet here, like paypal_io.configure) ----

def default_checker() -> AutoChecker:
    s = get_settings()
    return AutoChecker(SafeFetcher(allow_local=s.app_env == "dev"), github_token=s.github_token)


_checker_factory: Callable[[], AutoChecker] = default_checker


def configure(factory: Callable[[], AutoChecker] | None) -> None:
    global _checker_factory
    _checker_factory = factory or default_checker


def new_checker() -> AutoChecker:
    return _checker_factory()


# ---- input rules ----

def valid_deployed_url(url: str) -> bool:
    """Syntax only (no network in the request path): https with a host, or http://localhost in dev. The fetcher re-checks at fetch time."""
    from urllib.parse import urlsplit
    if not isinstance(url, str) or not (8 <= len(url) <= 500) or re.search(r"\s", url):
        return False
    parts = urlsplit(url)
    try:
        parts.port
    except ValueError:
        return False
    if not parts.hostname or parts.username is not None or parts.password is not None:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1") and get_settings().app_env == "dev"


def create_submission(db: Session, project: Project, member: ProjectMember, *, repo_url: str, commit_sha: str,
                      deployed_url: str, notes: str | None) -> tuple[Submission, Job]:
    contract = contract_service.get_contract(db, project.id)
    if contract is None or contract.signed_at is None or contract.freelancer_member_id != member.id:
        raise SubmissionError("NOT_THE_FREELANCER", "Only the freelancer named in the signed contract can submit work", 403)
    if project.state != "IN_PROGRESS":
        raise SubmissionError("PROJECT_STATE", f"Work can be submitted while the project is IN_PROGRESS (this one is {project.state})")
    attempts = db.scalar(select(func.count(Submission.id)).where(Submission.contract_id == contract.id)) or 0
    if db.scalars(select(Submission.id).where(Submission.contract_id == contract.id, Submission.state.in_(ACTIVE_STATES))).first():
        raise SubmissionError("SUBMISSION_ACTIVE", "A submission is still being checked")
    if attempts >= MAX_ATTEMPTS:
        raise SubmissionError("MAX_ATTEMPTS", f"All {MAX_ATTEMPTS} attempts are used; the lead decides what happens next")
    if parse_repo(repo_url) is None:
        raise SubmissionError("BAD_REPO_URL", "The repository must look like https://github.com/owner/repo", 422)
    if not SHA.match(commit_sha or ""):
        raise SubmissionError("BAD_COMMIT", "The commit must be 7 to 40 hexadecimal characters", 422)
    if not valid_deployed_url(deployed_url):
        raise SubmissionError("BAD_DEPLOYED_URL", "The live site must be an https URL", 422)
    if notes is not None and len(notes) > MAX_NOTES:
        raise SubmissionError("NOTES_TOO_LONG", f"Notes are limited to {MAX_NOTES} characters", 422)
    sub = Submission(contract_id=contract.id, attempt_no=attempts + 1, repo_url=repo_url.strip(), commit_sha=commit_sha.strip().lower(),
                     deployed_url=deployed_url.strip(), notes=(notes or "").strip() or None, state="SUBMITTED")
    db.add(sub)
    db.flush()
    ProjectService.transition(db, project, "VERIFYING", actor=f"user:{member.user_id}", reason=f"submission attempt {sub.attempt_no}")
    job = jobs.enqueue(db, "AUTO_CHECKS", {"submission_id": sub.id})
    return sub, job


# ---- which checks to run ----

def plan_checks(brd_content: dict, sub: Submission) -> list[dict]:
    """Defaults plus each criterion's hint, in a stable order, without duplicates. Pure."""
    planned: list[dict] = []
    seen: set = set()

    def add(check_type, requirement_code=None, criterion_id=None, **inputs):
        key = (check_type, requirement_code, criterion_id, tuple(sorted(inputs.items())))
        if key in seen or len(planned) >= MAX_CHECKS:
            return
        seen.add(key)
        planned.append({"check_type": check_type, "requirement_code": requirement_code, "criterion_id": criterion_id, "inputs": inputs})

    add("REPO_PUBLIC")
    add("COMMIT_EXISTS")
    add("URL_REACHABLE", path="/")
    for entry in brd_content.get("sitemap", []):
        add("URL_REACHABLE", path=entry["path"])
    for req in brd_content.get("requirements", []):
        for crit in req.get("acceptance_criteria", []):
            hint = crit.get("auto_check_hint")
            if not hint:
                continue
            t, path, text = hint.get("type"), hint.get("path"), hint.get("text")
            ids = dict(requirement_code=req["code"], criterion_id=crit["id"])
            if t == "URL_REACHABLE":
                add(t, path=path, **ids)
            elif t == "PAGE_CONTAINS":
                add(t, path=path, text=text, **ids)
            elif t == "FILE_EXISTS":
                add(t, path=path, **ids)
            elif t == "MOBILE_VIEWPORT":
                add(t, path=path or "/", **ids)
    return planned


def run_check(checker: AutoChecker, sub: Submission, item: dict) -> CheckResult:
    t, i, code = item["check_type"], item["inputs"], item["requirement_code"]
    if t == "REPO_PUBLIC":
        return checker.repo_public(sub.repo_url)
    if t == "COMMIT_EXISTS":
        return checker.commit_exists(sub.repo_url, sub.commit_sha)
    if t == "URL_REACHABLE":
        return checker.url_reachable(sub.deployed_url, i["path"], code)
    if t == "PAGE_CONTAINS":
        return checker.page_contains(sub.deployed_url, i["path"], i["text"], code)
    if t == "MOBILE_VIEWPORT":
        return checker.mobile_viewport(sub.deployed_url, i["path"], code)
    if t == "FILE_EXISTS":
        return checker.file_at_commit(sub.repo_url, sub.commit_sha, i["path"], code)[0]
    raise ValueError(f"unknown check type {t}")


def run_auto_checks(db: Session, submission_id: int, checker: AutoChecker | None = None) -> dict:
    """The AUTO_CHECKS job. Safe to retry: a half-finished run is cleared and redone; a finished one is left alone."""
    sub = db.get(Submission, submission_id)
    if sub is None:
        return {"effect": "SKIPPED", "why": "unknown submission"}
    if sub.state not in ("SUBMITTED", "AUTO_CHECKING"):
        return {"effect": "ALREADY_DONE", "state": sub.state}
    contract = db.get(Contract, sub.contract_id)
    brd = db.get(BRD, contract.brd_id)
    sub.state = "AUTO_CHECKING"
    db.execute(delete(AutoCheck).where(AutoCheck.submission_id == sub.id))
    checker = checker or new_checker()
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0}
    for item in plan_checks(brd.content_json, sub):
        r = run_check(checker, sub, item)
        counts[r.result] += 1
        db.add(AutoCheck(submission_id=sub.id, check_type=r.check_type, requirement_code=r.requirement_code,
                         input_json={**r.input, **({"criterion_id": item["criterion_id"]} if item["criterion_id"] else {})},
                         result=r.result, detail_json=r.detail))
    sub.state = "QUESTIONING"
    jobs.enqueue(db, "VERIFY_QUESTIONS", {"submission_id": sub.id})        # T-33: the questions follow the checks
    db.flush()
    return {"effect": "CHECKED", "submission_id": sub.id, **counts}


# ---- read side ----

def check_view(c: AutoCheck) -> dict:
    return {"id": c.id, "check_type": c.check_type, "requirement_code": c.requirement_code, "input": c.input_json,
            "result": c.result, "detail": c.detail_json, "created_at": c.created_at.isoformat()}


def submission_view(db: Session, s: Submission) -> dict:
    from app.services import evidence_service      # imported here: evidence_service imports this module
    checks = list(db.scalars(select(AutoCheck).where(AutoCheck.submission_id == s.id).order_by(AutoCheck.id)))
    summary = {r: sum(1 for c in checks if c.result == r) for r in ("PASS", "FAIL", "ERROR")}
    questions = list(db.scalars(select(VerificationQuestion).where(VerificationQuestion.submission_id == s.id).order_by(VerificationQuestion.id)))
    evidence = list(db.scalars(select(Evidence).where(Evidence.submission_id == s.id).order_by(Evidence.id)))
    return {"id": s.id, "contract_id": s.contract_id, "attempt_no": s.attempt_no, "state": s.state, "repo_url": s.repo_url,
            "commit_sha": s.commit_sha, "deployed_url": s.deployed_url, "notes": s.notes, "created_at": s.created_at.isoformat(),
            "auto_checks": [check_view(c) for c in checks], "auto_check_summary": summary,
            "questions": [evidence_service.question_view(q) for q in questions],
            "evidence": [evidence_service.evidence_view(e) for e in evidence], "report": None}   # report: T-34


def project_submissions(db: Session, project_id: int) -> list[Submission]:
    contract = contract_service.get_contract(db, project_id)
    if contract is None:
        return []
    return list(db.scalars(select(Submission).where(Submission.contract_id == contract.id).order_by(Submission.attempt_no)))
