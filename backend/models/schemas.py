"""Pydantic schemas for API requests and responses."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class CheckSubmissionRequest(BaseModel):
    team_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    access_code: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    team_id: str
    team_name: str
    token: str


class AdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    admin_id: str
    admin_name: str
    token: str


class BootstrapAdminRequest(BaseModel):
    bootstrap_secret: str = Field(..., min_length=1)
    admin_name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class CreateAdminRequest(BaseModel):
    admin_name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class AdminAccountResponse(BaseModel):
    admin_id: str
    admin_name: str
    email: str


class SubmitRequest(BaseModel):
    text: str = Field(..., min_length=1)
    gender: int = 0
    religional: int = 0
    caste: int = 0
    religion: int = 0
    appearence: int = 0
    socialstatus: int = 0
    amiguity: int = 0
    political: int = 0
    Age: int = 0
    Disablity: int = 0
    source_platform: Optional[str] = None
    comment: Optional[str] = None
    flag_duplicate: bool = False
    flag_pii: bool = False
    # Client-generated UUID (see frontend/src/lib/offlineQueue.js). Lets a
    # retried submit — after a network error where the response never made
    # it back, e.g. from the localStorage outbox queue — be recognized as
    # "already saved" instead of inserted twice.
    client_submission_id: Optional[str] = None


class SubmitResponse(BaseModel):
    id: str


class MyCountResponse(BaseModel):
    count: int


class MarkReviewedRequest(BaseModel):
    id: str
    reviewed: bool = True


class CreateTeamRequest(BaseModel):
    team_name: str = Field(..., min_length=1)
    member_emails: list[EmailStr] = Field(..., min_length=2, max_length=4)

    @field_validator("member_emails")
    @classmethod
    def dedupe_emails(cls, emails: list[EmailStr]) -> list[EmailStr]:
        seen = set()
        deduped = []
        for email in emails:
            key = str(email).lower()
            if key not in seen:
                seen.add(key)
                deduped.append(email)
        if len(deduped) < 2:
            raise ValueError("At least 2 distinct member emails are required.")
        return deduped


class TeamResponse(BaseModel):
    team_id: str
    team_name: str
    access_code: str
    member_emails: list[str] = Field(default_factory=list)
    email_sent: Optional[bool] = None


class DuplicateCheckResult(BaseModel):
    flagged: bool = False
    similarity: float = 0.0
    closest_match_snippet: str = ""


class PiiCheckResult(BaseModel):
    flagged: bool = False
    matched_terms: list[str] = Field(default_factory=list)


class CheckSubmissionResponse(BaseModel):
    duplicate: DuplicateCheckResult
    pii: PiiCheckResult


class QaBatchResponse(BaseModel):
    total_rows: int = 0
    flagged_duplicate: int = 0
    flagged_pii: int = 0
    updated_rows: int = 0


# --- Judging (post-event blind review) --------------------------------------


class CreateJudgeRequest(BaseModel):
    judge_name: str = Field(..., min_length=1)


class JudgeResponse(BaseModel):
    judge_id: str
    judge_name: str
    access_code: str


class JudgeLoginRequest(BaseModel):
    access_code: str = Field(..., min_length=1)


class JudgeLoginResponse(BaseModel):
    judge_id: str
    judge_name: str
    token: str


class JudgeQueueItem(BaseModel):
    """Blind view for a judge -- text only. Never includes the participant's
    labels, team_id, or team_name."""

    id: str
    text: str


class JudgeLabelRequest(BaseModel):
    submission_id: str = Field(..., min_length=1)
    gender: int = 0
    religional: int = 0
    caste: int = 0
    religion: int = 0
    appearence: int = 0
    socialstatus: int = 0
    amiguity: int = 0
    political: int = 0
    Age: int = 0
    Disablity: int = 0


class SampleForJudgingRequest(BaseModel):
    per_team: int = Field(default=10, ge=1, le=100)


class SampleForJudgingResponse(BaseModel):
    sampled: int
    teams_sampled: int
    teams_skipped_insufficient: int
