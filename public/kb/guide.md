# Guide

NP Autopilot is the New Programs team's knowledge base: one connected map of what Interview Kickstart teaches. It holds every program, course, module and topic, who owns them, which instructors teach them, and the live links to the slides, documents and folders that go with them. Everything in it traces back to a source: a KYP page in Confluence or a file the registry sheet points to. You do not need any technical knowledge to use it.

To edit this guide, change the one file `public/kb/guide.md` in the repository.

## How the knowledge base is built

The curriculum is a hierarchy:

- A **program** is what a learner signs up for (for example an Interview Preparation program). It contains **courses**, in order.
- A **course** contains **modules**, in order. A course can be reused by several programs.
- A **module** is one block of teaching. It covers **topics**, in order. A module that appears in several programs with the same content is one module; a module with the same title but different content is a **variant**, linked to the main (canonical) module.
- A **topic** can name **concepts**: for now, the tools and technologies it uses.
- **Resources** are the live links (Drive folders, Docs, Slides, Sheets, PDFs) attached to any of these.

A **domain** classifies programs, courses and modules. There are exactly four: **Fullstack**, **Backend**, **Frontend** and **Test**. A domain is a label, not a container: a module is "in" the Backend domain, it does not sit inside it. Searching for an old name of a domain still finds it.

Weeks are not part of the structure. When a program says which week it teaches a module, that week is stored on the program's own link to that course or module, and shown as program-specific information: "Week and order belong to each program, not to the module."

![A record's detail panel: where it belongs, its owners and SMEs, its topics, resources and sources](/kb/guide/record.png)

## Owners and SMEs

Two different kinds of people are linked to the curriculum, and they are never mixed up.

- An **owner** is a member of the Interview Kickstart New Programs team who is responsible for a program, course or module. A record can have several owners, and one person can own many records. Owners are always NP team member records, never instructors.
- An **SME** (subject-matter expert) is an instructor who teaches a module. A module can have several SMEs, and one instructor can be an SME for many modules. Every SME assignment has a role:
  - **Primary**: the main instructor for the module.
  - **Backup 1**, **Backup 2**, **Backup 3**: the backups, in order.
  - Another role, when a source names one (for example a role from the older sheets).

The database enforces this: it refuses an instructor as an owner, and an SME assignment without a role. When the sources list two primaries for one module, both are kept and the module is listed on **Data quality** so the team can decide.

To add or change them, open a program, course or module. Under **Owners**, choose **Add owner** and pick an NP team member. Under **SMEs** (modules only), choose **Add SME**, pick an instructor and choose the role; **Role** changes it and **Remove** takes it off. You need the contributor role or higher.

## Where the data comes from

- **The registry sheet** is the single list of sources. Every Drive folder, sheet, document and presentation the team uses is linked from it. The crawler reads it through the Google Sheets API, including links embedded in cells, and follows every link: all tabs of linked sheets, Drive folders with all their sub-folders and files, Docs, Slides, PDFs and Word files.
- **The KYPs** (Know Your Program pages in Confluence) are the reference for curriculum structure: each program's courses, modules, their order and topics, and the instructors it lists. Pages marked **[Do not Use]** are skipped and listed. Attachments are listed but not downloaded.
- Each source is stored as its **live link**, its id, its **version or last-modified time**, and how the registry reaches it. Copies made while reading are only temporary.
- **Re-crawling** reads everything again and compares each source by its id: a new version is read again, an unchanged one is not, and a source the registry no longer reaches is marked as removed (never deleted). Every link that cannot be read is recorded with the reason (no access, not found, unsupported format, missing shortcut target).
- **Relationships come from the sources, not from guesses.** A module belongs to a course because a KYP lists it there; a Drive folder belongs to a module because the registry's domain folder holds a folder named after that module. Every record and relationship the import made shows where it came from under **Sources** in its panel.

Admins see the whole catalog in **Admin → Sources & sync**: every source with its status (read, listed, deferred, failed, skipped), its version and the path that reaches it, and the failures with their reasons.

## Finding things

- **Home** opens on one big search box. Type and press Enter for the results, grouped by type. The chips below it repeat your recent searches and open each record type.
- Press **Ctrl K** (or **⌘K** on a Mac) anywhere to search every record and link by name or text. The same box runs commands like "New course".
- **Programs**, **Courses** and **Resources** in the sidebar list those records.
- **All records** is a table of everything. Use **Filter** to narrow it (by type, place, owner, tag, status, flagged). **Save view** keeps a set of filters as a tab.
- **Outline** shows programs and courses as a tree: a program's courses, their modules and topics, in order.
- **Map** is the read-only overview for everyone. Click a record on the map to see the same detail panel the workspace uses.
- **Who teaches what** is a table of instructors against modules: each cell shows the SME role (**P** Primary, **B1** to **B3** Backups, or the named role). Filter by domain, role or name, and export it as CSV.

![The Outline: a program's courses, modules and topics](/kb/guide/outline.png)

## The detail panel

Click any record, on any page, to open its detail panel. The Graph editor, the Map, the Admin pages and the record page all use the same panel. It shows, when the record has them:

- the **type**, **domain**, **description**, and for a variant the module it is a variant of;
- for a module: the courses and programs it is **used in** (with each program's week label), its **owners**, its **Primary SME** and **Backup SMEs** in order, its **topics**, its variants and live sessions;
- for a program: its **courses** in order, and the instructors its KYP lists;
- for a course: its **modules** in order and the programs that use it;
- for an instructor: the modules they are an SME for, with the role; for an NP team member: what they own;
- the **resources** (open the original live link) and the **sources** (the KYP page and version, or the registry file, it came from).

Sections without data are left out. Click a related record to move to it. **Open as a page** shows the same panel full width. Changes you make there appear everywhere, and stay after you close and reopen it.

## Creating and editing records

Click **New record** in the sidebar (or press **c**). Everything goes into one form and is saved in one step.

1. Choose the **Type** and type a **Name**. If a record with the same name already exists, the form tells you and offers to open it.
2. Under **Placement**, say where it belongs: a module in a course, a course in a program. You can create the parent right there.
3. Add **Relationships**, **Links**, **People** (owners and SMEs) and **Tags** if you have them.
4. Click **Create** (or press **Ctrl Enter**).

If anything is wrong, nothing is saved and the problem is highlighted. After saving, the message offers **Open** and, for a few seconds, **Undo**. Contributors send new records for approval: the button says **Send for approval**, and an editor reviews it in **Approvals**.

To edit a record, open it and change the name, description, fields, tags, owners or SMEs in place, or click **Edit**. A course or program can be saved as a **template** from its **…** menu; **New record → Start from** creates its courses, modules and topics too.

![The New record form, with an inline new course under Placement](/kb/guide/new-record.png)

## Links and relationships

To attach a link, open a record, go to **Links** and click **Add link**. Paste the URL: Drive files and folders, Docs, Sheets, Slides, GitHub, video and other websites are recognised. If the URL is already in the library, the form offers **Use existing** instead of a duplicate.

To connect two records, open one, go to **Relationships** and click **Connect**. Each choice reads as a sentence ("This module covers a topic"), and only the relationships allowed for the two types are offered. The built-in ones:

- **contains / part of**: the hierarchy (program → course → module → topic). Set it with Placement.
- **in domain**: a program, course or module belongs to one of the four domains.
- **variant of**: a program-specific version of a module points to the canonical module.
- **owned by**: a program, course or module and its NP team owners.
- **subject expert for**: an instructor is an SME for a module, with a role.
- **teaches**: an instructor listed by a program's KYP, or teaching a live session.
- **covers**: a module or topic covers a concept; topics found in a module's content.
- **requires**: one course, module or topic must come before another. **related to**: a looser connection.

Admins can add custom record types (**Settings → Record types**) and relationship types (type a new name in the relationship box). New types appear everywhere at once.

![Choosing a relationship: sentences grouped by direction](/kb/guide/relationship.png)

## The Graph editor

The **Graph editor** (in the Admin group, admins only) shows the whole knowledge base or one record and its neighbours, and lets admins edit there.

- Click a record to open its detail panel beside the graph. Double-click it to rename it.
- Double-click empty space to add a record. Hover a record and drag its connect handle onto another record to connect them; pairs that cannot be connected snap back with the reason.
- Drag records to arrange them. **Auto-layout** tidies everything, **Reset** forgets the saved positions, **Save view** keeps your own arrangement.
- **F** fits the graph to the screen, **/** searches, the minimap moves the view. The filters on the left narrow by type, by owner (NP team members) or by a course or program.
- Select records or relationships and press **Delete** to archive them; **Undo** is in the message that follows.

The server checks every change: only admins can arrange or edit the graph.

![Editing on the graph: a record's handle, the relationship picker and the legend with filters](/kb/guide/graph.png)

## The Admin area

The **Admin** group at the bottom of the sidebar opens the tools your role allows:

- **Overview**: one card per tool.
- **Approvals**: new records, changes and relationship types waiting for an editor or admin.
- **Data quality**: records without an owner, SME roles to check (two primaries, backups without a primary), missing required fields, broken links, flagged items and records not connected to anything.
- **Activity**: every change, who made it (a person, the AI assistant for a named person, an import, the sync, the system) and its before and after values.
- **Archived**: archived records; admins can restore them or delete them permanently.
- **Members**: roles and invitations (admins).
- **Sources & sync**: the source catalog and the sync's run log (admins).

## Roles

Everyone who signs in with an @interviewkickstart.com Google account is at least a viewer.

- **Viewer**: sees everything and can flag things as incorrect.
- **Contributor**: adds links, relationships, owners and SMEs directly; sends new records and field edits for approval.
- **Editor**: creates, edits, archives and restores directly, and approves proposals.
- **Admin**: everything an editor does, plus the Graph editor, record and relationship types, roles, the sources and the sync, and permanent deletion.

The database enforces the roles, whatever tool is used. The AI assistant acts with your role, but anything it archives waits for a person's approval.

## When someone else changed it first

If someone saves a change while you are editing the same record, a bar tells you. If you then save, you see **This record changed since you opened it** with both versions. Choose **Use their version**, or, as an editor, **Overwrite with mine**. Nothing is overwritten silently.

## Archive and permanent delete

- **Archive** (from a record's **…** menu) hides the record and its relationships and links from lists, the outline and the graph. You can **Undo** straight away or **Restore** it from **Archived**.
- Admins can **Delete permanently** from **Archived**, after typing the name to confirm. Large clean-ups follow a safety sequence: a backup that has been restored and checked, an export of everything to be removed, archiving, checks, and only then permanent deletion.

![Activity, filtered to updates, with a before and after for each changed field](/kb/guide/activity.png)

## Who to contact

For access, a new role or a new record type, ask a knowledge base admin; if you do not know who that is, ask the New Programs team. For problems with the app, contact the New Programs team.
