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
              "Embedded Systems"]
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
