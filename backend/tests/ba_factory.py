"""Builders for BA model outputs. Coverage vectors are in quarters (0..4) in D1..D10 order."""
from app.schemas.ba import DIMENSIONS

# The demo scene: round 0 scores 58, round 1 scores 79, round 2 scores 93 (each ≥ the previous, as answers only add detail)
R0 = (2, 1, 2, 3, 3, 2, 1, 3, 3, 3)
R1 = (2, 1, 2, 3, 4, 4, 4, 3, 4, 4)
R2 = (2, 4, 4, 4, 4, 4, 4, 3, 4, 4)


def dims(cov, refs=("L3-L5",)):
    return [{"dimension": d, "coverage": q / 4, "justification": f"{d} judged at {q}/4",
             "source_refs": list(refs) if q > 0 else []} for d, q in zip(DIMENSIONS, cov)]


def requirement(tid="R1", priority="MUST", by=(1,), criteria=("Given a visitor, when they open /stay, then rooms are listed",),
                refs=("L3",), title=None):
    return {"temp_id": tid, "title": title or f"Requirement {tid}", "description": "d", "priority": priority,
            "requested_by": list(by), "acceptance_criteria": list(criteria), "source_refs": list(refs)}


def conflict(resolved=False, resolution=None, topic="Online booking vs enquiry only"):
    return {"topic": topic, "positions": [{"member_id": 1, "position": "wants booking"},
                                          {"member_id": 2, "position": "no payments"}],
            "resolved": resolved, "resolution": resolution}


def output(cov=R2, *, members=(1, 2, 3), requirements=None, conflicts=None, out_of_scope=("Online payments",),
           budget=True, deadline=True, refs=("L3-L5",), injection=()):
    """A complete, gate-clean model output by default; override pieces to break a specific gate."""
    reqs = requirements if requirements is not None else [requirement("R1", by=members), requirement("R2", "SHOULD", by=members[:1], criteria=())]
    return {"dimensions": dims(cov, refs), "requirements": reqs, "conflicts": conflicts if conflicts is not None else [],
            "out_of_scope": list(out_of_scope), "budget_stated": budget, "deadline_stated": deadline,
            "injection_attempts": list(injection)}


def question(dimension="D5", text="Should visitors be able to book online, or only send an enquiry?", to=("ALL",),
             options=("Enquiry form only", "Online booking"), why="The sponsors disagree and the builder cannot guess."):
    return {"dimension": dimension, "question": text, "rationale": why, "addressed_to": list(to),
            "suggested_options": list(options) if options else None}


def questions(*qs):
    return {"questions": list(qs)}
