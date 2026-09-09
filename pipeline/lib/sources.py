"""Explicit registry of which sheet and column feeds which node type.

Deliberately hand-written, not discovered. A generic "any column whose header
looks like a name" sweep over this corpus yields 7,506 candidate people, of
which the overwhelming majority are learners and payroll employees (doc 08 Q2).
Freeform discovery is exactly the failure that put 27 slide bullets into the
reference implementation's instructor list.

Adding a source here is a deliberate act, and every entry is a claim that the
column means what its header says.
"""

# (relative_path, sheet, column_header, node_type)
#
# INSTRUCTOR — expanded 2026-09-09. The five original rosters plus the sheets
# that were in the unread 25. The AgenticAI workbook is the B4 blocker the
# `teaches` edge depended on: it was named as an edge source while the node type
# never read it.
INSTRUCTOR_SOURCES = [
    # --- the original five ---
    ("03-instructors/Instructors Directory.xlsx", "Responses", "Full Name"),
    ("03-instructors/SME database (For Ops + NP).xlsx", "Master", "Full Name"),
    ("05-operations/New Combined Schedule.xlsx", "Instructor Data", "Name"),
    ("02-curriculum/Resource Collection Mastersheet (Software + System).xlsx",
     "Indian Instructors", "Indian SME Name"),
    ("02-curriculum/Data and Management.xlsx", "Instructor Details", "Full Name"),
    # --- previously unread: AgenticAI Instructors Training Plan (18 sheets) ---
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", "SME Roster", "SME"),
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", "SME Roster - IND", "SME"),
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", "WIP_Training_Status", "Instructor"),
    # --- previously unread: SME Tracker ---
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Tracker - All roles", "Name"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "AI Enthusiasts", "Name"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Q2 - 25", "Candidate Name"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Q4-24", "Candidate Name"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Q3 2024", "Candidate Name"),
    # --- previously unread: SME interview audits ---
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "SME_Interview", "SME Name"),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "Agentic AI", "SME Name"),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "AI for Non-Tech Instructors", "SME Name"),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "Agentic AI IP", "SME Name"),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "Level_Up_SME_Interview", "SME Name"),
    # --- other declared instructor columns ---
    ("02-curriculum/Resource Collection Mastersheet (Software + System).xlsx",
     "Instructor(FullStack)", "Primary Instructor"),
    ("02-curriculum/Data and Management.xlsx", "Management  Instructors", "Instructor"),
    ("02-curriculum/Data and Management.xlsx", "PM India domain schedule", "Instructor Name"),
]

# MODULE — curriculum sheets whose Module Name column is authoritative.
MODULE_SOURCES = [
    ("02-curriculum/Resource Collection Mastersheet (Software + System).xlsx", s, "Module Name")
    for s in ["Full Stack Engineering", "Backend Engineering", "Test Engineering",
              "Cloud Engineering", "SRE Engineering", "Security Engineering",
              "Embedded Systems", "Frontend Engineering"]   # Frontend was missing
] + [
    ("02-curriculum/Data and Management.xlsx", s, "Module Name")
    for s in ["DABA", "PM India", "TPM", "PMTPM SD India", "EM"]
] + [
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", s, "Module name")
    for s in ["M_SME_App. GenAI", "M_SME_Adv.GenAI"]
]

# PERSON — only sheets that describe IK staff. Never a learner sheet.
PERSON_SOURCES = [
    ("00-master/IAims Setting Audit _ New Programs.xlsx", None, "Employee Name"),
]

#: Sheets deliberately NOT scanned for people, with the reason.
PERSON_EXCLUSIONS = {
    "05-operations/Operational Metrics.xlsx":
        "learner records — 12,986 rows of learner/coach/session, not staff",
    "06-analysis/MLSU_Gen AI_Agentic AI Classes Poll Feedback 2026.xlsx":
        "learner poll responses",
    "06-analysis/Domain Classes Poll Feedback 2026.xlsx":
        "learner poll responses",
}


# ---------------------------------------------------------------------------
# HIRING FUNNEL vs ROSTER — added 2026-09-09 after the instructor count hit 3,411.
#
# Two of the newly-added sources are not rosters. They are hiring funnels, and
# counting a funnel as its outcome is the same class of error as the reference
# implementation's 773 instructors. SME Tracker!Tracker - All roles holds 2,252
# named candidates of whom 294 read "Hire"; the SME_Interview audit sheets hold
# interview records with Reject / Shall proceed further.
#
# Every instructor candidate therefore carries pipeline_status, and only
# roster-backed or explicitly-hired people should be treated as deliverable.
# ---------------------------------------------------------------------------

#: sheet -> (outcome column header, {raw value: status})
FUNNEL_OUTCOMES = {
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Tracker - All roles"):
        ("Hiring Decision (PM)", {
            "hire": "hired", "decline": "rejected", "no show": "lapsed",
            "hold": "in_pipeline"}),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "SME_Interview"):
        ("Hiring Decision", {
            "shall proceed further": "hired", "reject": "rejected",
            "on hold": "in_pipeline", "dropped out": "lapsed"}),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "Agentic AI"):
        ("Hiring Decision", {
            "shall proceed further": "hired", "reject": "rejected",
            "on hold": "in_pipeline"}),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "Level_Up_SME_Interview"):
        ("Final Status", {
            "shall proceed further": "hired", "reject": "rejected",
            "on hold": "in_pipeline"}),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "Agentic AI IP"):
        ("Final Status", {"shall proceed further": "hired", "reject": "rejected"}),
    ("03-instructors/SME_Interview_Demo Audit Rubrics.xlsx", "AI for Non-Tech Instructors"):
        ("Hiring Decision", {"shall proceed further": "hired", "reject": "rejected"}),
}

#: Sources that ARE rosters — presence means the person is on the books.
ROSTER_SHEETS = {
    ("03-instructors/Instructors Directory.xlsx", "Responses"),
    ("03-instructors/SME database (For Ops + NP).xlsx", "Master"),
    ("05-operations/New Combined Schedule.xlsx", "Instructor Data"),
    ("02-curriculum/Resource Collection Mastersheet (Software + System).xlsx", "Indian Instructors"),
    ("02-curriculum/Data and Management.xlsx", "Instructor Details"),
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", "SME Roster"),
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", "SME Roster - IND"),
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx", "WIP_Training_Status"),
    ("02-curriculum/Resource Collection Mastersheet (Software + System).xlsx", "Instructor(FullStack)"),
    ("02-curriculum/Data and Management.xlsx", "Management  Instructors"),
    ("02-curriculum/Data and Management.xlsx", "PM India domain schedule"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "AI Enthusiasts"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Q2 - 25"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Q4-24"),
    ("03-instructors/SME Tracker - Bullseye_IK.xlsx", "Q3 2024"),
}

# ---------------------------------------------------------------------------
# MODULE -> DOMAIN. Explicit, because the curriculum sheet name IS the domain
# and nothing else in the corpus links a module to a program. `contains` is
# derived program -> domain -> module and every such edge is marked inferred.
# A sheet with no domain gets NO edge rather than a guessed one.
# ---------------------------------------------------------------------------
SHEET_DOMAIN = {
    "Backend Engineering": "Backend",
    "Cloud Engineering": "Cloud",
    "SRE Engineering": "SRE",
    "Security Engineering": "Security",
    "Test Engineering": "Test Engineering",
    "Embedded Systems": "Embedded",
    "Full Stack Engineering": "Fullstack",
    "Frontend Engineering": "Frontend",
    "DABA": "DABA",
    "TPM": "TPM",
    "EM": "EM",
    "PM India": "PM",
    "PMTPM SD India": "PM",
    # The two Agentic AI module sheets describe pathway products, not one of the
    # 42 owner-sheet domains. Left unmapped ON PURPOSE — a wrong join is worse
    # than a missing one (R12).
    "M_SME_App. GenAI": None,
    "M_SME_Adv.GenAI": None,
}


# ---------------------------------------------------------------------------
# TEACHES — module <-> instructor pairings, added 2026-09-10.
#
# The first build emitted 6 teaches edges from one sheet. Doc 05's other cited
# example, "Suresh Venkatesan -> SQL Programming", turned out to be REAL and
# sitting in a sheet no scan had ever opened. Ten sources exist; all are below.
#
# spec: (rel, sheet, header_row_1based, module_col_0based, [instructor_cols], domain_hint)
# instructor columns are ordered: the first is primary, the rest are backups.
# ---------------------------------------------------------------------------
_DM = "02-curriculum/Data and Management.xlsx"
_AG = "03-instructors/AgenticAI Instructors Training Plan.xlsx"
_RCM = "02-curriculum/Resource Collection Mastersheet (Software + System).xlsx"
_UP = "01-workflows/UpLevel Schedule Structure.xlsx"

TEACHES_GRIDS = [
    (_DM, "Data  Instructors", 1, 0, [1, 2, 3], "DABA"),
    (_DM, "Management  Instructors", 1, 0, [1, 2, 3, 4], "TPM"),
    (_AG, "2.0 US Module<>SME", 2, 0, [1, 2, 3, 4, 5, 6], None),
    (_AG, "WIP2.0 IND Module<>SME", 2, 0, [1, 2, 3, 4, 5, 6], None),
    (_AG, "M_SME_App. Agentic AI", 2, 0, [1, 2, 3, 4, 5, 6], None),
    (_AG, "IND_M_SME_Agentic AI", 2, 0, [1, 2, 3, 4, 5, 6], None),
    (_AG, "M_SME_App. GenAI", 2, 0, [1, 2, 3, 4, 5, 6], None),
    (_AG, "M_SME_Adv.GenAI", 2, 0, [1, 2, 3, 4, 5, 6], None),
    (_AG, "Preferred SMEs for Each Topic", 2, 0, [1], None),
    (_AG, "Preferred SMEs for Each Topic", 2, 5, [6], None),   # second block
    (_RCM, "Instructor(FullStack)", 1, 0, [1, 2, 3, 4], "Fullstack"),
    (_UP, "Resource Collections for FT Mas", 1, 0, [1], None),
    (_UP, "Resource Collections for Fast T", 1, 1, [2], None),
]

#: instructor -> multi-valued module list, split on the given separator
TEACHES_LISTS = [
    (_DM, "Instructor Details", "Full Name", "Topic expertise", ","),
    (_AG, "WIP_Training_Status", "Instructor", "Trained Modules", "/"),
]

# ---------------------------------------------------------------------------
# UpLevel Schedule Structure — 30 sheets, entered the corpus mid-analysis and
# went unscanned until 2026-09-10. 26 of its sheets are per-domain cohort
# schedules sharing one schema, and the SHEET NAME is the domain. The
# "Topic (For)" column is the best module evidence in the corpus.
# ---------------------------------------------------------------------------
UPLEVEL_DOMAIN_SHEETS = {
    "Machine Learning": "Machine Learning (IP course)", "PM": "PM", "TPM": "TPM",
    "PM Updates": "PM", "TPM Updates": "TPM", "EM-Regular": "EM", "EM-Upgrade": "EM",
    "iOS": "iOS", "Fullstack ": "Fullstack", "Android": "Android", "Backend": "Backend",
    "Frontend": "Frontend", "Cloud": "Cloud", "Embedded": "Embedded",
    "Test Engineering": "Test Engineering", "Test Engineering DSA": "Test Engineering",
    "SRE": "SRE", "Security Engineering": "Security",
    "Security Engineering SYSD": "Security", "Early Engineering": "Early Engineering",
    "Coding Pathway": "Coding Pathway", "System Design Pathway": "System Design Pathway",
    # Deliberately unmapped: no owner-sheet domain corresponds.
    " Masterclass": None, "Fast Track Masterclass": None, "India Cohort": None,
    "New DSA - Easier Version": None, "Domain Resource Collections": None,
    "Backend Domain Only (WIP)": None,
    "Resource Collections for FT Mas": None, "Resource Collections for Fast T": None,
}
UPLEVEL_TOPIC_COLUMN = "Topic (For)"


# ---------------------------------------------------------------------------
# EXPERT_IN — instructor -> domain, declared subject fields. Added 2026-09-10.
#
# 1,381 renderable instructors had no module edge, and 823 of them come from a
# single sheet. Two sheets list people without subject matter at MODULE level
# but do carry it at DOMAIN level:
#   Instructors Directory!Responses  Domain column, 85% filled — a Google Form
#   SME database!Master              Program column, 54% filled — an HR roster
# (rel, sheet, name_column, subject_column, basis, split_on)
# ---------------------------------------------------------------------------
EXPERT_IN_SOURCES = [
    ("03-instructors/Instructors Directory.xlsx", "Responses",
     "Full Name", "Domain", "self_declared", ","),
    ("03-instructors/SME database (For Ops + NP).xlsx", "Master",
     "Full Name", "Program", "hr_record", ","),
]

#: Role suffixes on the SME database Program column: "ML - Instructor" is the
#: domain ML plus a role. Stripped before joining; the recovery is reported.
#: Written as a PATTERN, not a word list — one of the words is also a doctype
#: value, and hardcoding it here would duplicate taxonomy vocabulary.
#: "Curricul\w+" deliberately covers the "Curriculam" misspelling in the sheet.
ROLE_SUFFIX_RE = (
    r"\s*[-\u2013]?\s*(Instructor|Curricul\w+|TAs?|Coach|Mentor|Trainer|SME)\s*$"
)
#: Program-column values that are a ROLE, not a domain. Never joined.
ROLE_ONLY_VALUES = {
    "teaching assistant", "career coach", "mock interviewer", "ta", "coach",
    "curriculum", "instructor", "sme", "na", "n/a", "others",
}


#: (rel, sheet, module_col) -> (rating_col, classes_col). Only one sheet in the
#: corpus records a per-instructor rating against a module. The first build read
#: it; generalising the pairing extractor dropped it, and eval Q15 caught that.
TEACHES_RATINGS = {
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx",
     "Preferred SMEs for Each Topic", 0): (2, 3),
    ("03-instructors/AgenticAI Instructors Training Plan.xlsx",
     "Preferred SMEs for Each Topic", 5): (7, 8),
}


# ---------------------------------------------------------------------------
# CLASS DELIVERY LOG — added 2026-09-10, and it is the largest teaches source
# in the corpus by a wide margin.
#
# 05-operations/New Combined Schedule.xlsx has 62 sheets. Only ONE ("Instructor
# Data", a bare name list) had ever been read. 44 of the others are per-domain
# CLASS SCHEDULES carrying "Instructor Name" against "Class Topic" — i.e. who
# actually taught what. 1,807 distinct pairs, 264 instructors, 824 topics,
# covering Backend, Frontend, Cloud, Security, Test, iOS, EM, TPM, Fullstack,
# Data Engineering and Machine Learning.
#
# Before this, all 668 teaches edges came from the AgenticAI workbook, so the
# graph had teaching evidence for Agentic AI and none for any domain we run at
# scale.
# ---------------------------------------------------------------------------
SCHEDULE_FILE = "05-operations/New Combined Schedule.xlsx"
SCHEDULE_INSTRUCTOR_COL = "Instructor Name"
SCHEDULE_TOPIC_COL = "Class Topic"
SCHEDULE_DATE_COL = "Date"   # class schedules record WHEN, which staffing needs

#: Sheets that are NOT a single domain's schedule.
SCHEDULE_NON_DOMAIN = {
    "Combined Schedule Mastersheet",   # every domain at once; kept, domain=None
    "Dashboard", "Sunday Monitors", "Career Coaching New Students",
    "Last Class Date", "Class Confirmation Record", "Delivery POC",
    "Instructor Data", "US Holiday",
}

#: Resource-type suffixes on a Class Topic. "Object Modeling Live Class" and
#: "Object Modeling Assignment Review Class" are the SAME module delivered in
#: two formats — strip the suffix so they resolve to one module node.
CLASS_SUFFIX_RE = (
    r"\s*[-\u2013]?\s*("
    r"live class(es)?|assignment review( class| session)?|test review( session)?|"
    r"pre[- ]?class|post[- ]?class|doubt (clearing )?session|"
    r"coaching( session)?|ars|tcs|dtc|ama|q\s*&\s*a|office hours|"
    r"class|session|workshop|lecture|review"
    r")\s*$"
)


# ---------------------------------------------------------------------------
# CLASS CONFIRMATION RECORD — the only availability signal in the corpus.
#
# 1,689 rows: 1,529 Confirmed, 160 Declined, 136 instructors. It is NOT a second
# delivery log — 126 of those instructors already carry teaches edges from the
# schedule sheets. What it adds is whether an instructor, when ASKED, said yes.
#
# Modelled as PROPERTIES on the instructor node, never as an edge type. It is
# scheduling friction, not a performance judgment, and any surface must say so.
# ---------------------------------------------------------------------------
CONFIRMATION_SHEET = "Class Confirmation Record"
CONFIRMATION_COLS = {"instructor": "Instructor", "status": "Status",
                     "date": "Date", "domain": "Domain", "id": "Confirmation ID"}
