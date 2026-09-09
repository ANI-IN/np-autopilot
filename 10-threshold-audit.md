# 10 — Threshold Audit

Every numeric cutoff in the pipeline, after two of them were found hiding correct
answers: the module `>= 2` cross-file rule, and the staffing `>= 2 taught
modules` filter that hid EM, the domain with exactly one instructor.

**The test each must pass:** *what would a correct answer excluded by this look
like?* If that question has an answer, the threshold does not filter — it ranks
or warns.

---

## Removed — filters that were dominated by false positives

These rejected instructor and person names outright. Sampling what they dropped
was decisive.

| threshold | dropped | what a correct answer excluded looked like |
|---|---|---|
| **sentence punctuation** | 127 distinct | `Dr. Raju Penmatcha` · `Chuhong Mai, PhD` · `Benjamin O. Tayo` · `Minh P. Vo` · `Arushi Prakash, Ph.D.` — **academic credentials and middle initials.** Nearly all real. |
| **contains a stopword** | 9 distinct | `Will Yao` · `Will Drevo` · `Will Carhart` · `Will (Guillermo) Monge` — **"will" is in the stopword list and is also a first name.** 4 of 9 were one person's name. |
| **more than 4 tokens** | 17 distinct | `Satya Sai Shiva Rama Akula` · `Tanikella V S S Pavan Kumar` · `Andrés Hernández-Schafhauser` · `Omar (عمر يسري عطية) Attia` |
| **single-token name** | 156 distinct | `Usha` — proven a person by a system-generated Confirmation ID. Also `Binoy`, `Ishaan`, `Dipti`, `Arun`. |
| **contains a digit** | 4 distinct | `2- Prateek` — a real name behind a numbering prefix. |
| **longer than 40 characters** | 9 distinct | All genuinely multi-name cells — but the real signal is the newline, not the length. |

**All six now flag instead of reject.** The candidate is retained and carries
`review`. **Result: instructor 3,488 → 3,817 (+329 real people recovered),
rejections 594 → 190, and 199 nodes now carry a visible review flag.**

---

## The bias, recorded — not just the count

The filters did not remove noise at random. **They had a shape**, and it ran for
several rounds. Re-applying the old rules to today's 3,817-name population:

### `sentence punctuation` — 126 people, and it is a credential filter

| category | count | examples |
|---|---|---|
| **academic or professional title** | **84** | `Abu Sayeed Mondol, PhD` · `Amelia W. Cole, Ph.D.` · `Dr. Raju Penmatcha` · `Amir Hadi Ph.D` |
| **middle initial** | **28** | `Benjamin O. Tayo` · `Minh P. Vo` · `Lawrence B. Chan` |
| other | 14 | |

**Two thirds of everyone this rule removed held a doctorate or a professional
title.** A rule intended to catch prose was, in practice, a filter on the most
credentialed instructors in the corpus — the ones most worth finding for a
staffing question.

### `contains a stopword` — 5 people, 4 of them named Will

`Will Yao` · `Will Drevo` · `Will Carhart` · `Will (Guillermo) Monge`.
**"will" is in the stopword list and is also a common first name.** This rule
was, for practical purposes, a filter on one name.

### `more than 4 tokens` — 22 people, disproportionately South Asian

`Achanta Sri Surya Srinivasa Sai Kiran` · `Satya Sai Shiva Rama Akula` ·
`Tanikella V S S Pavan Kumar` · `Sunil Madhu Sudhan Reddy G`, alongside
hyphenated European names like `Andrés Hernández-Schafhauser`. **A token-count
cap encodes an assumption that names are short, which is a culturally specific
assumption.**

### `single-token name` — 195 people

`Aakash`, `Aaron`, `Adam`, `Aditya`, `Agnivesh`, `Ahmed`. Mononyms and people
recorded by first name only. `Usha` was one, and a Confirmation ID later proved
her a person.

### Total

**336 of 3,817 people — 8.8% of the population — would still be excluded by the
six original rules.** Concentrated on people with academic credentials, people
with long multi-part names, and one first name.

**This is why "it only removes noise" is not a defence.** Noise removal that
correlates with a category of person is not noise removal.

---

## Kept as hard rejects — each excludes a shape that cannot be one person

| threshold | why it survives the test |
|---|---|
| contains `@` or `http` | An address is never a name. No correct answer looks like this. |
| newline in the cell | Genuinely several names in one cell — a parse failure, not a person. 21 cases. |
| matches the topic vocabulary | `Cloud`, `Database`, `Frontend`, `UI & DOM` in a name column. |
| no letters / numeric only / phone-shaped | `0`, `415-272-1398`, `1.0`. |
| column filler (`Back up 1`, `Option 2`) | Spreadsheet scaffolding. |
| module label shorter than 3 characters | No module is named `ab`. |

---

## Kept, but they RANK or WARN — they do not exclude

| threshold | role |
|---|---|
| `cross_validated = files >= 2` | A confidence **property** on the instructor node. Never filters. |
| `FUZZY_THRESHOLD = 0.70` | Proposes merges. **Nothing is ever applied**, so it cannot exclude. |
| middle-name variant | Proposes at **any** similarity, deliberately bypassing the threshold. |
| edge cap `CAP = 8` in the render | A display cap with `show N more` — **disclosed, not silent**. |
| search result limit 40 | Disclosed in the UI. |
| `>30%` contact-shaped column detection | Drops a **column**, and logs which. |

## Withdrawn

- **module `>= 2` cross-file** — never enforced in code; it only documented how
  the historic 234 figure was derived. `cross_validated` replaced it as a
  ranking signal.
- **staffing `>= 2` taught modules** — removed. It hid EM.

---

---

## The surviving 190 re-audited — and three were false positives

The principle *"hard rejects survive only where the shape cannot be the thing"*
was asserted, so it was tested by sampling every surviving category. **It did not
fully hold.**

| rejected | why it was wrong |
|---|---|
| `EM`, `PM`, `V2` (module, <3 chars) | **`EM` and `PM` are real labels.** A length cap excluded legitimate abbreviations. Now a review flag. |
| `Shelby` (instructor) | The collision resolver treated a **single token** as "not a person" and dropped the instructor side. One token is ambiguous in both directions — `Shelby` is a person, `Frontend` is a topic. Both readings are now kept and flagged. |
| `JS and Web Development` (module) | The topic vocabulary lacked `web` and `js`, so it was classified a **person name** and dropped from the module side. Vocabulary extended. |

All four recovered. **Rejections 190 → 185, and every remaining one was checked
by hand.** The principle now holds — but it took testing it to find that it
didn't.

---

## The rule this produced

> **A threshold may rank. A threshold may warn. A threshold must not silently
> exclude.** If something falls below a cutoff, say so in the output rather than
> dropping it.

Recorded in `CLAUDE.md`. Both cases that motivated it were found by an
unrehearsed question, not by review — which is the argument for the fresh eval
set continuing.
