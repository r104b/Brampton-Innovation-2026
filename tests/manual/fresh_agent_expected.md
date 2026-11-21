# Fresh-agent snapshot test: human reviewer guide

This is one manual acceptance test for the checked-in synthetic snapshot at
state version 7. It has not been executed merely by adding these files.
Automated renderer tests do not demonstrate fresh-agent file access or reasoning.

## Run the test

1. Open a new coding-agent session with its workspace set to
   `C:\Brampton_innovation_2026\Brampton-Innovation-2026`.
2. Do not attach this conversation, this expected-answer file, or the JSON fixture.
3. Paste only the contents of `tests/manual/fresh_agent_prompt.txt` as the prompt.
4. Inspect the session's file-reading actions. Confirm it actually opens
   `AGENTS.md` and `context/CURRENT_STATE.md`, plus `CLAUDE.md` if applicable.
   Merely saying it read them is insufficient. If read actions are unavailable,
   record access as unverified rather than claiming a pass.
5. Compare the response against the checklist below. Do not require exact prose;
   Markdown-escaped IDs such as `del\-sms` and plain `del-sms` are equivalent.

This test explicitly directs the agent to the files. Passing proves it can read
and interpret this snapshot in that session; it does not prove automatic file
discovery in every agent, current live database freshness, or the entire pipeline.

## Expected results

- [ ] Identifies the data as **synthetic**, not live client state or repository
  implementation progress. Project: `demo-project`, Fictional Booking Demo;
  schema version `1`, state version `7`, as of `2026-11-21T15:00:00+00:00`
  (equivalent UTC notation is acceptable).
- [ ] Open: `del-sms`, SMS booking confirmations; source `gmail-001`, evidence
  `ev-sms`.
- [ ] In progress: `del-calendar`, calendar integration; source
  `synthetic-calendar`, evidence `ev-calendar`.
- [ ] Blocked: `del-reminder`, booking reminders, awaiting the client answer to
  `q-timing`; source `synthetic-reminder`, evidence `ev-reminder`.
- [ ] Implemented, QA pending: `del-booking`, booking form; source
  `synthetic-booking`, evidence `ev-booking`. Does not call it verified.
- [ ] QA verified: `del-validation`, required field validation; passing QA
  reference `synthetic-qa` / `ev-qa`; requirement reference
  `synthetic-validation` / `ev-validation`.
- [ ] Open consent question: `q-timing`, whether reminders may be sent 24 hours
  before the appointment; source `synthetic-timing`, evidence `ev-timing`.
  Does not invent approval.
- [ ] Answered question: `q-timezone`, timezone is `America/Toronto`; answer
  source `synthetic-timezone`, evidence `ev-timezone`.
- [ ] Active decision: `dec-current`, use email and SMS confirmations; source
  `synthetic-current`, evidence `ev-current`. Supersedes `dec-old`, email only;
  historical source `synthetic-old`, evidence `ev-old`.
- [ ] `review-001` proposes removing SMS, but is pending human review and has
  **not** changed the active decision; source `synthetic-conflict`, evidence
  `ev-conflict`.
- [ ] Launch date and approver: **Not enough verified information.** No such
  date or approval is in the snapshot; does not invent a citation or approver.
- [ ] Makes no edits and calls no external service.

Pass only if file access is observed and every expected result is satisfied.
Identifiers must match exactly after removing Markdown escape backslashes.
For example, `synthetic-gmail-001` is not equivalent to `gmail-001` and fails
the SMS citation check even if the rest of the interpretation is correct.
If the snapshot changes, update this reviewer guide to the new version before
using it to score another run. Do not feed the expected answers to the agent.

## Record the result

- Agent/tool and model:
- Run date:
- Workspace:
- Snapshot version:
- File-read actions observed:
- Response or session reference:
- Result: NOT RUN / PASS / FAIL / ACCESS UNVERIFIED
- Failed checks or limitations:

An independent run with a second coding agent can reuse the same prompt and
checklist. Record it separately.
