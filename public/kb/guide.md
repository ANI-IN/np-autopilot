# Guide

The knowledge base is where the curriculum team keeps track of what we teach: every program, course, module, week and live session, the slides, recordings and briefs that go with them, and who owns what. This guide explains how to use it. You do not need any technical knowledge.

To edit this guide, change the one file `public/kb/guide.md` in the repository.

## The basics

There are three kinds of things in the knowledge base.

- **Records** are the building blocks: a program, a course, a domain, a module, a week, a live session, a topic, an instructor. Each record has a type, a name, an owner and, depending on its type, some extra fields.
- **Relationships** connect two records and say how they relate: a course **contains** a module, an instructor **teaches** a session, a module **covers** a topic.
- **Links** (also called resources) are the files and pages that go with a record: KYP slides, a class recording, an assignment brief, a solutions repository on GitHub, a page on UpLevel.

One example, from top to bottom: the course **System Design for Senior Engineers** contains the module **Scalability Fundamentals**, which contains **Week 1 · Caching and load balancing**, which contains the live session **Designing a URL shortener**. That session has two links: its slides and its recording.

![A record's detail panel: where it belongs, its owner and fields, then tabs for links, relationships and history](/kb/guide/record.png)

## Finding things

- Press **Ctrl K** (or **⌘K** on a Mac) anywhere to search every record and link by name or text. The same box runs commands like "New course" or "Go to Outline".
- **All records** is a table of everything. Use **Filter** to narrow it (by type, course, owner, tag, status, flagged); each filter shows as a chip you can remove. **Save view** keeps a set of filters as a tab; tick "Share with the team" to let everyone use it.
- In a table, press **j** and **k** to move, **Enter** to open, **x** to select, and **/** to jump to the search box.
- **Outline** shows programs and courses as a tree. It is the quickest way to see a whole course at once.
- **Graph** shows what a record is connected to. Click a record to open it; double-click to expand its neighbours.

![The Outline: a program's courses, modules, weeks and sessions](/kb/guide/outline.png)

## Creating records

Click **New record** in the sidebar (or press **c**). Everything goes into one form and is saved in one step.

1. Choose the **Type** and type a **Name**. If a record with the same name already exists, the form tells you and offers to open it.
2. Under **Placement**, say where it belongs. Start typing a course, module or week name and pick it. If it does not exist yet, choose **Create "…"** to create it right there; you can do this at every level (for example, a new week inside a new module inside an existing course). A record can belong to more than one place: use **Add another place**.
3. Add **Relationships**, **Links**, **People** and **Tags** if you have them. Each section shows how many items it holds.
4. Click **Create** (or press **Ctrl Enter**). Use **Create and add another** to enter several in a row.

If anything is wrong, nothing is saved and the problem is highlighted, so you can fix it and try again. After saving, the message at the bottom offers **Open** and, for a few seconds, **Undo**.

If you are a **contributor**, the button says **Send for approval**: an editor reviews your new record in **Approvals** before it appears.

The form saves a draft on your computer as you type. If you close it by accident, the next New record offers to restore it.

![The New record form, with an inline new course under Placement](/kb/guide/new-record.png)

## Adding links

Every link has a **URL**, a **title**, a **kind** and two short texts:

- the **description** says what is inside the link ("90 slides, with speaker notes");
- the **purpose** says why it is attached to this particular record ("shown in the first half of the class").

Paste the URL and the knowledge base recognises where it lives and picks an icon and a likely kind: Google Drive files and folders, Docs, Sheets, Slides, **UpLevel** (uplevel.interviewkickstart.com), GitHub, YouTube or other video, Zoom recordings, live class links, or any website. Change the **Kind** if the guess is wrong: KYP slides / lecture deck, speaker notes, recording, live class link, assignment brief, problem statement, solution, evaluation criteria, question bank, interview guide, reading or reference doc.

If the URL is already in the library, the form offers **Use existing** instead of making a duplicate. Use **Pick from library** to attach a link that is already there.

To add a link to an existing record, open it, go to the **Links & resources** tab and click **Add link**.

## Connecting records

Open a record, go to **Relationships** and click **Connect**. Choose the relationship (only the ones allowed for this type are offered), then the other record. The sentence under the row shows what you are about to say, for example "Ada Example teaches Designing a rate limiter".

What the built-in relationships mean:

- **contains / part of**: where something sits in a course. Set this with Placement.
- **covers**: a course, module or session covers a topic or domain.
- **teaches**: an instructor teaches a course, module or session.
- **subject expert for**: an instructor reviews or advises on the content.
- **requires**: one course, module or topic must come before another.
- **related to**: a looser connection.

The same pair cannot be connected twice the same way, and pairs a relationship does not allow are not offered.

## When someone else changed it first

Two people can have the same record open. If someone saves a change while you are editing, a blue bar tells you. If you then save, you see **This record changed since you opened it**, with your version next to theirs. Choose **Use their version** (then re-apply your change), or, if you are an editor, **Overwrite with mine**. Nothing is ever overwritten silently.

## Archive and permanent delete

- **Archive** (from a record's **…** menu) hides the record from lists, the outline and the graph, along with its relationships and links. The confirmation shows exactly how many go with it. Nothing is deleted, and you can **Undo** straight away or **Restore** later.
- Everything archived is on the **Archived** page. Admins can **Delete permanently** from there. You have to type the name to confirm, the dialog lists what is removed with it, and the deletion is recorded.

Removing a single relationship or link from a record is immediate and offers **Undo**.

## Record types and fields

Admins can add their own record types in **Settings → Record types**, for example a "Case Study" with fields such as Difficulty (a choice of Easy, Medium or Hard), Minutes (a number) and Brief URL. A type has a name, an icon, a colour, its fields (each with a label, a kind, help text and whether it is required), where it can be placed, and who owns new records. The form preview on the right shows what the New record form will look like.

New types appear everywhere at once: the New record form, table filters, search, the graph, the outline, CSV export, Data quality and the AI assistant.

Changing a type that is already in use is safe. Renaming is fine. Removing a field hides it and keeps its data. A new required field never blocks existing records; it lists them on Data quality. A type in use cannot be archived until its records are moved with **Change type of N records**. Editors can propose type changes; an admin approves them in Approvals.

![Settings → Record types, editing a type with a live preview of its form](/kb/guide/types.png)

## Roles

- **Viewer**: sees everything, can flag things as incorrect.
- **Contributor**: edits records, adds links and relationships, and sends new records and archive requests for approval.
- **Editor**: creates and archives directly, approves proposals, and can overwrite a conflicting change.
- **Admin**: everything an editor does, plus record types, roles and permanent deletion.

## Keeping things accurate

- **Data quality** lists records without an owner, missing required fields, broken links, flagged items and records that are not connected to anything. Fix the top of each list first.
- If something is wrong and it is not yours, open it and choose **Flag as incorrect** from the **…** menu. The owner gets a review in **Approvals → Reviews**.
- Every record shows a **completeness** score: owner, summary, required fields, links and placement. A course's score covers everything inside it.
- A course or program can be saved as a **template** from its **…** menu, and a new course can start from it under New record → Start from.

## Who to contact

For access, a new role or a new record type, ask a knowledge base admin (listed in Settings → Members). For problems with the app, contact the New Programs team.
