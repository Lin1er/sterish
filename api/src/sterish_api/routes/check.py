from fastapi import APIRouter, HTTPException, Query
from .models import CheckResponse, SkillResponse, SkillListItem
from ..client import query_skill, query_all_skills, query_skill_count

router = APIRouter()


@router.get("/check/{skill_id}", response_model=CheckResponse)
async def check_skill(skill_id: str):
    """Check the audit status and trust score of a skill."""
    skill = query_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    return CheckResponse(
        skill_id=skill["skill_id"],
        verdict=skill["latest_verdict"],
        trust_score=skill["trust_score"],
        evidence=skill.get("evidence_url", ""),
        audit_timestamp=skill.get("audit_timestamp", ""),
        auditor=skill.get("auditor", ""),
    )


@router.get("/skills", response_model=list[SkillListItem])
async def list_skills(
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List all registered skills with pagination."""
    skills = query_all_skills(start, limit)
    return [
        SkillListItem(
            skill_id=s["skill_id"],
            verdict=s["latest_verdict"],
            trust_score=s["trust_score"],
            versions=len(s.get("versions", [])),
        )
        for s in skills
    ]
