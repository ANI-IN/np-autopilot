# Guide

The knowledge base is where the curriculum team keeps track of what we teach: every program, course, module, week and live session, the slides, recordings and briefs that go with them, and who owns what. This guide explains how to use it. You do not need any technical knowledge.

To edit this guide, change the one file `public/kb/guide.md` in the repository.

## The basics

There are three kinds of things in the knowledge base.

- **Records** are the building blocks: a program, a course, a domain, a module, a week, a live session, a topic, an instructor. Each record has a type, a name, an owner and, depending on its type, some extra fields.
- **Relationships** connect two records and say how they relate: a course **contains** a module, an instructor **teaches** a session, a module **covers** a topic.
- **Links** are the files and pages that go with a record: KYP slides, a class recording, an assignment brief, a solutions repository on GitHub, a page on UpLevel. One link can be attached to several records; the **Links** page lists each one once.

One example, from top to bottom: the course **System Design for Senior Engineers** contains the module **Scalability Fundamentals**, which contains **Week 1 · Caching and load balancing**, which contains the live session **Designing a URL shortener**. That session has two links: its slides and its recording.

![A record's detail panel: where it belongs, its owner and fields, then tabs for links, relationships and history](/kb/guide/record.png)

## Finding things

- Press **Ctrl K** (or **⌘K** on a Mac) anywhere to search every record and link by name or text. The same box runs commands like "New course" or "Go to Outline".
- **All records** is a table of everything. Use **Filter** to narrow it (by type, course, owner, tag, status, flagged); each filter shows as a chip you can remove. **Save view** keeps a set of filters as a tab; tick "Share with the team" to let everyone use it.
- In a table, press **j** and **k** to move, **Enter** to open, **x** to select, and **/** to jump to the search box.
- **Outline** shows programs and courses as a tree. It is the quickest way to see a whole course at once.
- **Graph** shows the whole knowledge base, or one record and what it is connected to. Click a record to open it; the **+** next to a record expands its neighbours (if you cannot edit, double-clicking a record does the same).
- **Who teaches what** is a table of instructors against modules and live sessions. Each cell shows the role from the current mastersheet (**P** primary, **B1**–**B3** backups) or **T** when an older sheet says they taught it. Filter by domain, role or name, and export it as CSV.
- **Program timeline** shows each program's modules week by week, with their live sessions and slide decks.

![The Outline: a program's courses, modules, weeks and sessions](/kb/guide/outline.png)

## Creating records

Click **New record** in the sidebar (or press **c**). Everything goes into one form and is saved in one step.

1. Choose the **Type** and type a **Name**. If a record with the same name already exists, the form tells you and offers to open it.
2. Under **Placement**, say where it belongs. Start typing a course, module or week name and pick it. If it does not exist yet, choose **Create "…"** to create it right there; you can do this at every level (for example, a new week inside a new module inside an existing course). A record can belong to more than one place: use **Add another place**.
3. Add **Relationships**, **Links**, **People** and **Tags** if you have them. Each section shows how many items it holds.
4. Click **Create** (or press **Ctrl Enter**). Use **Create and add another** to enter several in a row.

If anything is wrong, nothing is saved and the problem is highlighted, so you can fix it and try again. After saving, the message at the bottom offers **Open** and, for a few seconds, **Undo**.

If you are a **contributor**, the button says **Send for approval**: an editor reviews your new record in **Approvals** before it appears. The same goes for your changes to an existing record's fields: they wait in **Approvals** until an editor applies them. Links and relationships you add to existing records are saved straight away.

The form saves a draft on your computer as you type. If you close it by accident, the next New record offers to restore it.

![The New record form, with an inline new course under Placement](/kb/guide/new-record.png)

## Adding links

Every link has a **URL**, a **title**, a **kind** and two short texts:

- the **description** says what is inside the link ("90 slides, with speaker notes");
- the **purpose** says why it is attached to this particular record ("shown in the first half of the class").

Paste the URL and the knowledge base recognises where it lives and picks an icon and a likely kind: Google Drive files and folders, Docs, Sheets, Slides, **UpLevel** (uplevel.interviewkickstart.com), GitHub, YouTube or other video, Zoom recordings, live class links, or any website. Change the **Kind** if the guess is wrong: KYP slides / lecture deck, speaker notes, recording, live class link, assignment brief, problem statement, solution, evaluation criteria, question bank, interview guide, reading or reference doc.

If the URL is already in the library, the form offers **Use existing** instead of making a duplicate. Use **Pick from library** to attach a link that is already there.

To add a link to an existing record, open it, go to the **Links** tab and click **Add link**.

## Connecting records

Open a record, go to **Relationships** and click **Connect**. Type in the relationship box to search. Each choice reads as a sentence, grouped by direction: "This module covers a topic" under **This module …**, and "An instructor teaches this module" under **… this module**. Only the ones allowed for this type are offered. Then pick the other record. The sentence under the row shows what you are about to say, for example "Ada Example teaches Designing a rate limiter".

![Choosing a relationship: sentences grouped by direction, with Create relationship at the end](/kb/guide/relationship.png)

### A relationship that does not exist yet

Type its name, for example "mentors", and choose **Create relationship "mentors"**. Give the name it reads the other way ("mentored by" is suggested for you) and the two kinds of record it connects (filled in from the records you are connecting).

- **Admins**: it is available to everyone straight away.
- **Editors**: you can use it straight away. It is marked **Awaiting review** and appears in **Approvals**, where an admin confirms it, renames it, or merges it into an existing one.
- **Contributors**: it is sent to an admin as a proposal. Nobody can use it until it is approved.

Names that already exist are refused, including small differences: "Teaches", "teach" and "taught by" all match **teaches / taught by**. You are offered the existing one instead. Admins can **Merge** two relationship types in **Settings → Relationship types**: every relationship moves to the one you keep, with a count first, and the merge is recorded in Activity.

What the built-in relationships mean:

- **contains / part of**: where something sits in a course. Set this with Placement.
- **covers**: a course, module or session covers a topic or domain.
- **teaches**: an instructor teaches a course, module or session.
- **subject expert for**: an instructor reviews or advises on the content.
- **requires**: one course, module or topic must come before another.
- **related to**: a looser connection.

The same pair cannot be connected twice the same way, and pairs a relationship does not allow are not offered.

## Editing on the graph

The **Graph** page shows the records around one record, and you can edit there as well as look. Everything uses the same rules, permissions and history as the forms.

- **Add a record**: double-click empty space (or press **N**), choose the type, type the name and press **Create**. **More…** opens the full New record form. The record appears where you clicked.
- **Connect two records**: hover a record and drag its connect handle onto another record. Choose the relationship, or **Create relationship…**. If the two kinds of record cannot be connected, the graph says why and the line snaps back.
- **Open or rename**: click a record to open its panel beside the graph. Double-click it to rename it in place. Click a relationship to see it as a sentence, edit its note or remove it.
- **Archive**: select one or more records or relationships (shift-click, or shift-drag a box) and press **Delete**. The confirmation shows what goes with them. **Undo** is in the message that follows.
- **Arrange**: drag records around. Positions are saved for everyone in the shared layout, or in a **saved graph view** of your own. They never change the records. **Auto-layout** tidies everything; **Reset** forgets the saved positions.
- **Find your way**: **F** fits the graph to the screen, **/** searches (and loads the record if it is not shown yet), the minimap moves the view, and the filters on the left narrow by type, relationship, owner or course. The **+** next to a record expands or collapses its neighbours. Arrow keys move the selected records, and **Esc** clears the selection.

Changes other people make appear on your graph as they happen. A record someone is editing has a dashed green ring, and hovering it shows who.

![Editing on the graph: a record's handle, the relationship picker and the legend with filters](/kb/guide/graph.png)

## When someone else changed it first

Two people can have the same record open. If someone saves a change while you are editing, a blue bar tells you. If you then save, you see **This record changed since you opened it**, with your version next to theirs. Choose **Use their version** (then re-apply your change), or, if you are an editor, **Overwrite with mine**. Nothing is ever overwritten silently.

## Legacy records and the sync

Most records come from the original NP Autopilot site, and a **sync** copies its changes in every hour (admins can also press **Sync now** in **Settings → Sync**). Only what changed is written. If you edited a record here and it also changed at the source, your edit is kept and the record is listed under **Sync conflicts** on Data quality. A record that disappears from the source is never deleted here: it is marked for review and listed under **Removed at the source**, and you decide whether to archive it. A relationship or link that disappears from the source is archived, and can be restored from **Archived**. The sync never brings back something you archived, and never touches records created here.

A **legacy** record comes from the older sheets only (for example an instructor with no role in the current mastersheet, or a programme from the older sheets). It carries a **Legacy** badge. Lists and the graph show current records; in **All records** use **Filter → Current and legacy** (or **Legacy only (older sheets)**), on the **Graph** tick **Show legacy**, and in **Who teaches what** tick **Include legacy (older sheets)**. Legacy is not the same as archived: a legacy record is still live and can be edited; an archived one is hidden until someone restores it.

With the owner's approval, the legacy domains and legacy modules are deleted permanently (only the four current domains stay), and the sync is told never to bring them back. Legacy instructors, topics, sessions and programmes stay. If a record sat inside a deleted one, it is kept and listed on Data quality so you can give it a new place.

## Archive and permanent delete

- **Archive** (from a record's **…** menu) hides the record from lists, the outline and the graph, along with its relationships and links. The confirmation shows exactly how many go with it. Nothing is deleted, and you can **Undo** straight away or **Restore** later.
- Everything archived is on the **Archived** page. Admins can **Delete permanently** from there. You have to type the name to confirm, the dialog lists what is removed with it, and the deletion is recorded.

Removing a single relationship or link from a record is immediate and offers **Undo**. If you are a contributor, it is sent to **Approvals** instead, like any other archive.

## Record types and fields

Admins can add their own record types in **Settings → Record types**, for example a "Case Study" with fields such as Difficulty (a choice of Easy, Medium or Hard), Minutes (a number) and Brief URL. A type has a name, an icon, a colour, its fields (each with a label, a kind, help text and whether it is required), where it can be placed, and who owns new records. The form preview on the right shows what the New record form will look like.

New types appear everywhere at once: the New record form, table filters, search, the graph, the outline, CSV export, Data quality and the AI assistant.

Changing a type that is already in use is safe. Renaming is fine. Removing a field hides it and keeps its data. A new required field never blocks existing records; it lists them on Data quality. A type in use cannot be archived until its records are moved with **Change type of N records**. Editors can propose type changes; an admin approves them in Approvals.

![Settings → Record types, editing a type with a live preview of its form](/kb/guide/types.png)

## Roles

Everyone who signs in with an @interviewkickstart.com Google account is at least a viewer.

- **Viewer**: sees everything, can flag things as incorrect, and can claim their own person record (**Claim this profile**; an admin confirms it).
- **Contributor**: attaches links and adds relationships to existing records directly; sends new records, field edits, archive requests and new relationship types for approval. The database enforces this, whatever tool is used.
- **Editor**: creates, edits, archives and restores directly, approves proposals, and can overwrite a conflicting change. An editor's changes to record types go to an admin for approval.
- **Admin**: everything an editor does, plus record types (including which types should have an owner), relationship type review and merges, roles, people's e-mail addresses (**Settings → People**), profile claims, the sync (**Settings → Sync**), and permanent deletion. Admins also see a **Map** button at the top of the sidebar that goes back to the NP Autopilot map, and the map has a matching **Workspace graph** button at the top that opens the Graph page.

Admins give roles in **Settings → Members**. To add someone who has not signed in yet, invite them by their @interviewkickstart.com address with a role: the role applies the first time they sign in. The last admin cannot be removed or made a lower role; make someone else an admin first.

The AI assistant (Claude with your API token, **Settings → API tokens**) acts with your role, but anything it archives always waits for a person's approval, and it can never approve, change roles, start a sync or delete permanently.

## Keeping things accurate

- **Data quality** lists records without an owner, missing required fields, broken links, flagged items and records that are not connected to anything. Fix the top of each list first.
- If something is wrong and it is not yours, open it and choose **Flag as incorrect** from the **…** menu. The owner gets a review in **Approvals → Reviews**.
- Every record shows a **completeness** score: owner, summary, required fields, links and placement. A course's score covers everything inside it.
- A course or program can be saved as a **template** from its **…** menu, and a new course can start from it under New record → Start from.

## Activity

**Maintain → Activity** lists every change: who made it (a person, the AI assistant working for a named person, an import, the sync, or the system), what they did, to which record (with a link, or marked **deleted** if it is gone), and when. Hover the time to see the exact date. For an update, each changed field shows its value before and after.

Filter by person, action, what changed (a record, a relationship, a link, a type…), source (app, AI assistant, import, sync, system) and dates, or search names and values. **Export CSV** downloads exactly what is shown.

Admins see all activity. Editors see their own changes and everything about the courses and records they own. Everyone else sees a record's history in its **History** tab, which lists entries the same way. Nobody, admins included, can edit or delete an entry.

![Activity, filtered to updates, with a before and after for each changed field](/kb/guide/activity.png)

## Who to contact

For access, a new role or a new record type, ask a knowledge base admin; if you do not know who that is, ask the New Programs team. For problems with the app, contact the New Programs team.
