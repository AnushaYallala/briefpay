"""Builders for BRD model drafts (what the Generator returns, before code assembles it)."""


def criterion(given="a visitor opens the contact page", when="they fill in the enquiry form and send it",
              then="a confirmation with a reference number is shown", evidence=("SCREENSHOT", "CODE_SNIPPET"), hint=None):
    return {"given": given, "when": when, "then": then, "evidence": list(evidence), "auto_check_hint": hint}


def draft_requirement(title="Enquiry form", priority="MUST", ids=("R1",), by=(1,), criteria=None, weight=4,
                      refs=("L3-L5",), description="Visitors can send an enquiry without paying online."):
    if criteria is None:
        criteria = [criterion(hint={"type": "PAGE_CONTAINS", "path": "/contact", "text": "Send enquiry"})] if priority == "MUST" else []
    return {"from_temp_ids": list(ids), "title": title, "description": description, "priority": priority, "weight": weight,
            "requested_by": list(by), "acceptance_criteria": criteria, "source_refs": list(refs)}


def draft(members=(1, 2, 3), requirements=None, **over):
    """A complete draft covering analysis requirements R1 and R2 (R1 MUST, R2 SHOULD)."""
    reqs = requirements if requirements is not None else [
        draft_requirement("Gallery of rooms", "SHOULD", ids=("R2",), by=members[:1], weight=2),
        draft_requirement("Enquiry form", "MUST", ids=("R1",), by=members, weight=5),
    ]
    base = {
        "title": "Velugu Cove tourism website",
        "executive_summary": "One simple website that shows the cove's homestay, restaurant and boat tours and lets visitors send an enquiry.",
        "business_goals": ["Help visitors find the cove's businesses", "Let visitors get in touch easily"],
        "success_measures": ["At least 20 enquiries a month by the end of the first season"],
        "stakeholders": [{"member_id": members[0], "business_name": "Sea Breeze Homestay", "needs": ["Show my rooms", "Let guests contact me"]}],
        "audience": "Tourists from nearby cities, on phones, reading English and Telugu.",
        "sitemap": [{"path": "/", "purpose": "Welcome and links to everything"}, {"path": "/stay", "purpose": "The homestay and its rooms"},
                    {"path": "/contact", "purpose": "The enquiry form"}],
        "non_functional": ["Works well on mobile phones"],
        "content_responsibilities": [{"item": "Room photos and prices", "owner_member_id": members[0], "due": "Nov 20"}],
        "out_of_scope": ["Online payments on the site"],
        "open_items": [],
        "glossary": [{"term": "Enquiry", "definition": "A message from a visitor asking about a stay, meal or tour."}],
        "requirements": reqs,
        "hosting": None, "domain": None,
    }
    base.update(over)
    return base
