from fastapi import APIRouter, HTTPException, Query

from ..client import query_all_skills, query_skill
from ..models import CheckResponse, SkillListItem, SkillVersionResponse

router = APIRouter()


def _to_check_response(skill: dict) -> CheckResponse:
    return CheckResponse(
        skill_id=skill["skill_id"],
        verdict=skill["latest_verdict"],
        trust_score=skill["trust_score"],
        evidence_hash=skill.get("evidence_hash", ""),
        evidence=skill.get("evidence_url", ""),
        audit_timestamp=skill.get("audit_timestamp", 0),
        auditor=skill.get("auditor", ""),
        versions=[
            SkillVersionResponse(
                version=v["version"],
                content_hash=v["content_hash"],
                registered_at=v["registered_at"],
            )
            for v in skill.get("versions", [])
        ],
    )


@router.get("/check/{skill_id}", response_model=CheckResponse)
async def check_skill(skill_id: str) -> CheckResponse:
    """Check the audit status and trust score of a skill."""
    skill = query_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return _to_check_response(skill)


@router.get("/skills", response_model=list[SkillListItem])
async def list_skills(
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SkillListItem]:
    """List registered skills with pagination."""
    skills = query_all_skills(start, limit)
    return [
        SkillListItem(
            skill_id=s["skill_id"],
            verdict=s["latest_verdict"],
            trust_score=s["trust_score"],
            versions=len(s.get("versions", [])),
            audit_timestamp=s.get("audit_timestamp", 0),
        )
        for s in skills
    ]
