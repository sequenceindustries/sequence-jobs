"""Job-seeker profile: a strict whitelist of fields needed for the features. Protected characteristics are refused."""
from __future__ import annotations

from typing import Any

from .normalise import PROVINCES

# Never collected and never used for ranking. Naming them in a request gets an explicit rejection.
PROTECTED = {"gender", "sex", "race", "ethnicity", "religion", "age", "birth_date", "date_of_birth", "disability",
             "marital_status", "pregnancy", "nationality", "id_number", "sexual_orientation", "political_opinion",
             "health", "photo", "culture", "language_home"}

LIST_FIELDS = {"categories": 10, "skills": 40, "skills_absent": 40, "qualifications": 10, "cities": 10, "industries": 10}
ENUM_LISTS = {"work_modes": {"remote", "hybrid", "on_site"},
              "employment_types": {"full_time", "part_time", "contract", "internship", "temporary", "graduate"},
              "provinces": set(PROVINCES.values())}
LEVELS = {"entry", "junior", "mid", "senior"}


class ProfileError(Exception):
    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code, self.message, self.fields = code, message, fields or []


def validate_profile(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProfileError("invalid", "Profile must be an object.")
    banned = sorted(k for k in raw if k.lower() in PROTECTED)
    if banned:
        raise ProfileError("protected_field", "We do not collect or use personal characteristics such as these to "
                                              "recommend or rank jobs.", banned)
    allowed = set(LIST_FIELDS) | set(ENUM_LISTS) | {"experience_level", "years_experience", "salary_expectation",
                                                    "career_goals"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ProfileError("unknown_field", "These fields are not part of the profile.", unknown)

    out: dict[str, Any] = {}
    for f, cap in LIST_FIELDS.items():
        if f in raw:
            if not isinstance(raw[f], list) or not all(isinstance(x, str) for x in raw[f]):
                raise ProfileError("invalid", f"{f} must be a list of text values.", [f])
            seen, vals = set(), []
            for x in raw[f]:
                v = " ".join(x.split())[:60].lower() if f in ("skills", "skills_absent", "qualifications", "categories") \
                    else " ".join(x.split())[:60]
                if v and v.lower() not in seen:
                    seen.add(v.lower()); vals.append(v)
            out[f] = vals[:cap]
    for f, allowed_vals in ENUM_LISTS.items():
        if f in raw:
            if not isinstance(raw[f], list) or any(x not in allowed_vals for x in raw[f]):
                raise ProfileError("invalid", f"{f} contains an unsupported value.", [f])
            out[f] = sorted(set(raw[f]))
    if "experience_level" in raw:
        if raw["experience_level"] not in LEVELS | {None}:
            raise ProfileError("invalid", "experience_level must be entry, junior, mid or senior.", ["experience_level"])
        out["experience_level"] = raw["experience_level"]
    if "years_experience" in raw:
        y = raw["years_experience"]
        if y is not None and (not isinstance(y, (int, float)) or isinstance(y, bool) or not 0 <= y <= 50):
            raise ProfileError("invalid", "years_experience must be a number from 0 to 50.", ["years_experience"])
        out["years_experience"] = y
    if "salary_expectation" in raw:
        se = raw["salary_expectation"]
        if se is not None:
            if not isinstance(se, dict) or set(se) - {"min", "period"} or se.get("period") not in ("month", "year", "hour") \
                    or not isinstance(se.get("min"), (int, float)) or isinstance(se.get("min"), bool) or not 0 < se["min"] < 10_000_000:
                raise ProfileError("invalid", "salary_expectation must be {min: number, period: month|year|hour}.",
                                   ["salary_expectation"])
        out["salary_expectation"] = se
    if "career_goals" in raw:
        cg = raw["career_goals"]
        if cg is not None and (not isinstance(cg, str) or len(cg) > 500):
            raise ProfileError("invalid", "career_goals must be text up to 500 characters.", ["career_goals"])
        out["career_goals"] = cg
    overlap = set(out.get("skills", [])) & set(out.get("skills_absent", []))
    if overlap:
        raise ProfileError("conflict", "A skill cannot be both held and marked as not held: " + ", ".join(sorted(overlap)),
                           ["skills", "skills_absent"])
    return out
