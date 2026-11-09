"""Load the demo story into the database (T-52).

    cd backend
    .venv/Scripts/python scripts/seed.py
    .venv/Scripts/python scripts/seed.py --repo https://github.com/<you>/<repo> --site https://<your-site> --commit-1 <sha> --commit-2 <sha> --paypal-email <freelancer-sandbox-email>

Needs a migrated database (`alembic upgrade head`) and DEMO_MODE on. Creates two projects:
  * "Velugu Cove tourism website"              a first campaign that missed its deadline: holds released, nothing charged
  * "Velugu Cove tourism website (build phase)" funded ($400 captured), two submissions (NEEDS_CHANGES, then VERIFIED): ready for payout
Nothing here talks to PayPal. Running it twice changes nothing. Log in as any of the printed emails (no password in this app).
Use the commit ids and site of the real sample site (T-60) so the evidence matches what a visitor sees.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.services.seed_demo import DEFAULT_COMMITS, DEFAULT_REPO, DEFAULT_SITE, SeedError, seed_demo  # noqa: E402


def main(argv: list[str] | None = None, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=DEFAULT_REPO, help="GitHub URL of the sample site's repository")
    ap.add_argument("--site", default=DEFAULT_SITE, help="deployed URL of the sample site")
    ap.add_argument("--paypal-email", default=None, help="the freelancer's REAL PayPal sandbox email (the demo payout goes there)")
    ap.add_argument("--commit-1", default=DEFAULT_COMMITS[0], help="commit of the first (rejected) attempt")
    ap.add_argument("--commit-2", default=DEFAULT_COMMITS[1], help="commit of the second (accepted) attempt")
    args = ap.parse_args(argv)
    db = SessionLocal()
    try:
        result = seed_demo(db, repo_url=args.repo, site_url=args.site, commits=(args.commit_1, args.commit_2),
                           freelancer_paypal_email=args.paypal_email)
        db.commit()
    except SeedError as e:
        db.rollback()
        out(f"Not seeded: {e}")
        return 1
    except (OperationalError, ProgrammingError) as e:
        db.rollback()
        out(f"The database is not ready ({type(e).__name__}). Run `alembic upgrade head` first.")
        return 2
    finally:
        db.close()
    out("Already seeded: nothing changed." if result.get("already_seeded") else "Seeded.")
    out(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
