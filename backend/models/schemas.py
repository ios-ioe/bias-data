"""Pydantic schemas for API requests and responses."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class CheckSubmissionRequest(BaseModel):
    team_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class LoginRequest(BaseModel):
    access_code: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    team_id: str
    team_name: str
    token: str


class AdminLoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    token: str


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
    source_date: Optional[str] = None
    flag_duplicate: bool = False
    flag_pii: bool = False


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
