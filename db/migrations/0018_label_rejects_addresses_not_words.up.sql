-- 0018 — `label_not_contact` rejected the word HTTP.
--
-- 0002 wrote `check (label !~ '@' and lower(label) !~ 'http')`. The intent is
-- in the name: a node label must not carry contact data. The TEST was the
-- character `@` and the substring `http`, and against the 75-file corpus that
-- cost nothing, because no label in it contained either.
--
-- The row-B content graph has 5,811 nodes and 116 of them fail it:
--
--     114 labels contain `http`  — of which only 10 are a URL. The other 104
--                                  are the PROTOCOL, in a real title:
--                                  'HTTP Methods and Error Codes',
--                                  'Common HTTP response codes used with REST:'
--       2 labels contain `@`     — '@SURUCHI' and '@Tim', instructor mentions
--                                  written into a slide title. Not addresses.
--
-- Breakdown by type: 44 file, 31 content_topic, 27 live_class, 12 slide_deck.
--
-- A guard this shape does not fail safe. Under it the only way to project the
-- content graph is to drop 116 real nodes or to disable the constraint, and
-- the second is what actually happens under deadline. `CLAUDE.md` §4 is the
-- rule it breaks: a threshold may rank or warn, it may exclude only when the
-- shape cannot be the thing at all — and 'HTTP Methods and Error Codes'
-- plainly can be a topic.
--
-- SO THE TEST BECOMES THE THING IT WAS ALWAYS DESCRIBING:
--
--     an ADDRESS   local@domain.tld   rather than the character `@`
--     a URL        https?://          rather than the substring `http`
--
-- This is NARROWER, and narrowing a contact guard is an owner decision, not a
-- refactor. Approved by Animesh Kumar on 2026-09-29; the note and its negative
-- controls are in `docs/CONTACT-DATA.md` §L.
--
-- NEGATIVE CONTROLS — these must still be REJECTED after this migration:
--     'someone@example.org'                        (email shape)
--     'profile https://example.com/in/x'           (URL scheme; a real
--                                                   profile URL is the case
--                                                   that matters and is NOT
--                                                   written out here)
-- and these must now PASS:
--     'HTTP Methods and Error Codes'               (protocol, not a URL)
--     'Introduction to Cloud Testing: @Tim'        (mention, not an address)
--
-- THE TEN LABELS THAT REALLY CARRY A URL ARE NOT DROPPED. Pass 7 cleans the
-- label and keeps the original in provenance (`label_raw` plus the source
-- record), so the node survives and the citation back to the file is intact —
-- `CLAUDE.md` §1, a failed join is visible, a deleted node is not.
--
-- APPLIES IN THREE PLACES AND THIS IS ONE OF THEM. The same rule is in
-- `pipeline/validate.py` and in pass 7's label cleaner; this is the one that
-- cannot be bypassed by a code path that forgets.
-- ---------------------------------------------------------------------------

alter table nodes drop constraint if exists label_not_contact;

alter table nodes
    add constraint label_not_contact
    check (
        label !~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
        and label !~* 'https?://'
    );

comment on constraint label_not_contact on nodes is
    'A label may not carry an ADDRESS (local@domain.tld) or a URL (https?://). '
    'Narrowed from "any @ or any http" on 2026-09-29 — the old test rejected '
    'the word HTTP in 104 legitimate titles. docs/CONTACT-DATA.md section L.';
