import re


DEGREE_ONLY_TOKENS = {
    "btech",
    "mtech",
    "mba",
    "b",
    "m",
    "tech",
    "bachelor",
    "master",
    "degree",
    "program",
    "programme",
    "branches",
    "branch",
    "related",
    "eligible",
    "all",
    "and",
    "or",
    "the",
    "of",
}


def normalize_label(value: str) -> str:
    if not value:
        return ""

    text = value.lower().strip()
    text = text.replace("&", " and ")
    text = text.replace("/", " ")
    text = re.sub(r"[^a-z0-9\s+]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    replacements = {
        "ai ml": "aiml",
        "ai and ml": "aiml",
        "artificial intelligence and machine learning": "aiml",
        "artificial intelligence machine learning": "aiml",
        "cse aiml": "cse aiml",
        "computer science and engineering": "cse",
        "computer science": "cse",
        "information technology": "it",
        "electronics and communication": "ece",
        "electronics and electrical": "eee",
        "electrical and electronics": "eee",
        "b tech": "btech",
        "b.tech": "btech",
        "m tech": "mtech",
        "m.tech": "mtech",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text).strip()


def student_branch_tokens(branch: str, degree: str = "") -> set:
    text = normalize_label(f"{degree} {branch}")
    tokens = set(text.split())

    if "cse" in tokens and "aiml" in tokens:
        tokens.update({"cse", "aiml", "cse aiml"})
    if "cse" in tokens and "core" in tokens:
        tokens.update({"cse", "core", "cse core"})
    if "cse" in tokens and ("ds" in tokens or "data" in tokens):
        tokens.update({"cse", "data science"})

    return tokens | {text}


def eligibility_tokens(labels) -> set:
    tokens = set()

    for label in labels or []:
        normalized = normalize_label(str(label))
        if not normalized:
            continue

        tokens.add(normalized)
        for part in normalized.split():
            if part not in DEGREE_ONLY_TOKENS:
                tokens.add(part)

        # "CSE/IT related" style phrases
        if "related" in normalized or "all cse" in normalized:
            tokens.update({"cse", "it"})
        if "cse it" in normalized or "cse and it" in normalized:
            tokens.update({"cse", "it"})

    return {token for token in tokens if token and token not in DEGREE_ONLY_TOKENS}


def degree_is_eligible(student_degree, eligible_degrees) -> bool:
    if not eligible_degrees:
        return True

    student_norm = normalize_label(student_degree or "")
    if not student_norm:
        return False

    for label in eligible_degrees:
        label_norm = normalize_label(str(label))
        if not label_norm:
            continue
        if label_norm in student_norm or student_norm in label_norm:
            return True
        # B.Tech vs btech already normalized
        if set(label_norm.split()) & set(student_norm.split()):
            return True

    return False


def branch_is_eligible(student_branch, student_degree, placement) -> bool:
    """
    Return True if the student's branch/degree fits the email criteria.
    If the email lists no branch/degree limits, treat as open.
    """
    if not student_branch:
        return False

    open_all = bool(placement.get("open_to_all_branches"))
    eligible_branches = placement.get("eligible_branches") or []
    eligible_degrees = placement.get("eligible_degrees") or []

    if open_all and not eligible_branches and not eligible_degrees:
        return True

    if not eligible_branches and not eligible_degrees:
        # No criteria extracted → do not block on branch
        return True

    if not degree_is_eligible(student_degree, eligible_degrees):
        return False

    if not eligible_branches:
        return True

    student_tokens = student_branch_tokens(student_branch, student_degree or "")
    branch_tokens = eligibility_tokens(eligible_branches)

    # Broad CSE/IT related bucket
    related = any(
        "related" in normalize_label(str(label))
        or "cse it" in normalize_label(str(label))
        for label in eligible_branches
    )

    if related:
        if student_tokens & {"cse", "it", "aiml", "core", "cse aiml", "cse core"}:
            return True

    for token in branch_tokens:
        if not token or token in DEGREE_ONLY_TOKENS:
            continue
        if len(token) < 2:
            continue
        if token in student_tokens:
            return True
        for student_token in student_tokens:
            if student_token in DEGREE_ONLY_TOKENS or len(student_token) < 2:
                continue
            if token == student_token:
                return True
            if len(token) >= 3 and len(student_token) >= 3:
                if token in student_token or student_token in token:
                    return True

    return False


def filter_students_by_eligibility(students, placement):
    matched = []
    skipped = []

    for student in students:
        if branch_is_eligible(
            student.get("branch"),
            student.get("degree"),
            placement
        ):
            matched.append(student)
        else:
            skipped.append(student)

    return matched, skipped
