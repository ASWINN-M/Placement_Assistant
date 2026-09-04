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
    "students",
    "only",
    "batch",
    "year",
}


# Canonical branch families — student matches only via set intersection.
BRANCH_PATTERNS = [
    (r"\bcse\s*(ai\s*/?\s*ml|aiml|ai\s*&\s*ml)\b", "cse_aiml"),
    (r"\bcse\s*data\s*science\b|\bcse\s*\(?\s*ds\s*\)?\b", "cse_ds"),
    (r"\bdata\s*science\b", "cse_ds"),
    (r"\bcse\s*core\b|\bcs\s*core\b", "cse_core"),
    (r"\bcomputer\s*science(?:\s*and\s*engineering)?\b|\bcse\b", "cse"),
    (r"\belectronics\s*(?:and|&)?\s*communication\b|\bece\b", "ece"),
    (r"\belectrical\s*(?:and|&)?\s*electronics\b|\beee\b", "eee"),
    (r"\bmechanical(?:\s*engineering)?\b|\bmech\b", "mech"),
    (r"\bcivil(?:\s*engineering)?\b", "civil"),
    (r"\bchemical(?:\s*engineering)?\b", "chemical"),
    (r"\bbiotechnology\b|\bbiotech\b", "biotech"),
]


FAMILY_EXPAND = {
    "cse": {"cse", "cse_core", "cse_aiml", "cse_ds"},
    "cse_core": {"cse_core"},
    "cse_aiml": {"cse_aiml"},
    "cse_ds": {"cse_ds"},
    "it": {"it"},
    "ece": {"ece"},
    "eee": {"eee"},
    "mech": {"mech"},
    "civil": {"civil"},
    "chemical": {"chemical"},
    "biotech": {"biotech"},
}


CSE_SPECS = {"cse_core", "cse_aiml", "cse_ds"}
ALL_CSE = {"cse", "cse_core", "cse_aiml", "cse_ds"}
CSE_IT_RELATED = ALL_CSE | {"it"}

LABEL_MAP = {
    "cse": "CSE",
    "cse_core": "CSE Core",
    "cse_aiml": "CSE AI/ML",
    "cse_ds": "CSE Data Science",
    "it": "IT",
    "ece": "ECE",
    "eee": "EEE",
    "mech": "Mechanical",
    "civil": "Civil",
    "chemical": "Chemical",
    "biotech": "Biotech",
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
        "b tech": "btech",
        "m tech": "mtech",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text).strip()


def detect_branch_families(text: str) -> set[str]:
    """Map free text to canonical branch families."""
    if not text:
        return set()

    normalized = normalize_label(text)
    if not normalized:
        return set()

    found = set()
    for pattern, family in BRANCH_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            found.add(family)

    # IT is easy to false-positive on the word "it" — only clear forms.
    if re.search(r"\binformation\s*technology\b", normalized):
        found.add("it")
    if re.search(r"\bcse\s*(?:/|and|&)?\s*it\b|\bit\s*(?:/|and|&)?\s*cse\b", normalized):
        found.add("it")
    if re.search(r"(?<![A-Za-z])IT(?![A-Za-z])", text):
        found.add("it")
    if re.search(r"\bb\.?\s*tech\s+it\b|\bit\s+related\b", normalized):
        found.add("it")

    return found


def expand_families(families: set[str]) -> set[str]:
    expanded = set()
    for family in families:
        expanded.update(FAMILY_EXPAND.get(family, {family}))
    return expanded


def email_families_from_detection(families: set[str]) -> set[str]:
    """
    Email side:
    - "CSE" alone → all CSE specializations (Core, AI/ML, DS)
    - "CSE Core" / "CSE AI/ML" / "CSE DS" → that track only
    - "CSE/IT related" handled separately via CSE_IT_RELATED
    """
    specs = families & CSE_SPECS
    others = families - ALL_CSE

    if specs:
        # Specific CSE track(s) mentioned — do not also treat bare "cse"
        # from the same phrase (e.g. "CSE Core" matches both patterns).
        return specs | others

    if "cse" in families:
        # Generic CSE only → every CSE specialization
        return set(ALL_CSE) | others

    return expand_families(families)


def email_branch_families(eligible_branches) -> set[str]:
    """Allowed student families from email branch labels."""
    allowed = set()

    for label in eligible_branches or []:
        text = str(label)
        normalized = normalize_label(text)
        if not normalized:
            continue

        related = (
            "related" in normalized
            or "cse it" in normalized
            or re.search(r"\bcse\b.*\bit\b|\bit\b.*\bcse\b", normalized)
        )

        families = detect_branch_families(text)
        if related and (
            families & {"cse", "it", "cse_core", "cse_aiml", "cse_ds"} or not families
        ):
            # CSE/IT related → all CSE tracks + IT, plus any other branches
            # listed in the same label (rare).
            allowed.update(CSE_IT_RELATED)
            allowed.update(email_families_from_detection(families) - ALL_CSE - {"it"})
        else:
            allowed.update(email_families_from_detection(families))

    return allowed


def student_branch_families(branch: str, degree: str = "") -> set[str]:
    """
    Student side keeps their actual track.
    CSE Core / AI/ML / DS do not collapse into each other.
    """
    families = detect_branch_families(f"{degree} {branch}")
    specs = families & CSE_SPECS
    others = families - ALL_CSE

    if specs:
        return specs | others

    return expand_families(families) | others


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
        if set(label_norm.split()) & set(student_norm.split()):
            return True

    return False


def text_says_open_to_all(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(
            r"\b(all\s+branches|open\s+to\s+all(?:\s+branches)?|"
            r"any\s+branch|all\s+b\.?\s*tech\s+branches)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def guess_branches_from_text(text: str) -> list[str]:
    """Backup when Groq returns empty eligible_branches."""
    if not text:
        return []

    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    focus_lines = [
        line
        for line in lines
        if re.search(
            r"eligible|branch(?:es)?\s*:|criteria|streams?\s*:",
            line,
            flags=re.IGNORECASE,
        )
    ]
    scan = "\n".join(focus_lines) if focus_lines else "\n".join(lines[:8])

    families = detect_branch_families(scan)
    if not families:
        if re.search(
            r"cse\s*/\s*it|cse\s*(?:and|&)\s*it|cse/it\s+related",
            scan,
            re.I,
        ):
            return ["CSE/IT related"]
        return []

    normalized = normalize_label(scan)
    if "related" in normalized and (families & {"cse", "it"}):
        labels = ["CSE/IT related"]
        other = families - {"cse", "it", "cse_core", "cse_aiml", "cse_ds"}
        labels.extend(
            LABEL_MAP[family]
            for family in sorted(other)
            if family in LABEL_MAP
        )
        return labels

    return [
        LABEL_MAP[family]
        for family in sorted(families)
        if family in LABEL_MAP
    ]


def enrich_placement_eligibility(
    placement: dict,
    subject: str = "",
    body: str = "",
) -> dict:
    """Fill missing branch criteria from email text."""
    placement = dict(placement or {})
    text = f"{subject or ''}\n{body or ''}"

    branches = placement.get("eligible_branches") or []
    if not branches:
        guessed = guess_branches_from_text(text)
        if guessed:
            placement["eligible_branches"] = guessed
            print(f"i Inferred eligible branches from email text: {guessed}")

    if not placement.get("open_to_all_branches") and text_says_open_to_all(text):
        placement["open_to_all_branches"] = True
        print("i Email says open to all branches.")

    return placement


def branch_is_eligible(
    student_branch,
    student_degree,
    placement,
    allow_if_unspecified: bool = False,
) -> bool:
    """
    Strict branch check.

    Fail closed when branches are unknown (unless Excel shortlist).
    Mechanical never matches CSE/IT criteria.
    """
    if not student_branch:
        return False

    open_all = bool(placement.get("open_to_all_branches"))
    eligible_branches = placement.get("eligible_branches") or []
    eligible_degrees = placement.get("eligible_degrees") or []

    if not degree_is_eligible(student_degree, eligible_degrees):
        return False

    if open_all:
        return True

    if not eligible_branches:
        return bool(allow_if_unspecified)

    student_families = student_branch_families(
        student_branch,
        student_degree or "",
    )
    allowed_families = email_branch_families(eligible_branches)

    if not allowed_families:
        return bool(allow_if_unspecified)

    return bool(student_families & allowed_families)


def filter_students_by_eligibility(
    students,
    placement,
    allow_if_unspecified: bool = False,
):
    matched = []
    skipped = []

    for student in students:
        if branch_is_eligible(
            student.get("branch"),
            student.get("degree"),
            placement,
            allow_if_unspecified=allow_if_unspecified,
        ):
            matched.append(student)
        else:
            skipped.append(student)

    return matched, skipped
