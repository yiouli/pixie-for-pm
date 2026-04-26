# User Interview Synthesis Handbook

A step-by-step, executable guide for turning raw interview recordings into product decisions. No prior synthesis experience required.

---

## Before You Start: What You Need

**Inputs you should have:**

- Audio/video recordings or written transcripts from user interviews
- Any notes you or a notetaker took during the interviews
- Your original research questions (the reason you ran the interviews)

**Tools you'll need (pick one from each row):**

| Purpose                       | Free option                                               | Paid option                 |
| ----------------------------- | --------------------------------------------------------- | --------------------------- |
| Transcription                 | Otter.ai (free tier), Google Docs voice typing            | Rev.com, Grain, Dovetail    |
| Clustering / affinity mapping | Google Jamboard, sticky notes on a wall, Miro (free tier) | FigJam, Dovetail, Miro paid |
| Tracking sheet                | Google Sheets                                             | Airtable, Notion database   |
| Final deliverable             | Google Docs, Markdown                                     | Notion, Confluence          |

**Time estimate:** Plan for roughly 2-3x the total interview duration. If you ran 8 interviews of 45 minutes each (6 hours of recordings), expect 12-18 hours of synthesis work spread across several sessions.

---

## Phase 1: Prepare Your Tracking Infrastructure

**Do this once before you start processing any interviews.**

### Step 1.1 — Create a master tracking spreadsheet

Open a new spreadsheet. Create the following columns:

| Column                | What goes here                                | Example                                                           |
| --------------------- | --------------------------------------------- | ----------------------------------------------------------------- |
| Participant ID        | Anonymous label                               | P01, P02, P03                                                     |
| Interview Date        | When you spoke                                | 2025-04-15                                                        |
| Role / Segment        | Their relevant category                       | "Solo founder," "Sr. Eng at Series B"                             |
| Key Quote             | One standout verbatim quote                   | "I don't trust the eval scores because I can't see why it failed" |
| Surprise              | Something you didn't expect                   | Uses spreadsheets for eval tracking instead of any tool           |
| Top Pain Point        | Their single biggest frustration              | Can't reproduce failures from eval runs                           |
| Current Workaround    | How they solve the problem today              | Manual spot-checking of 10 random outputs                         |
| Willingness to Change | How motivated they are to adopt something new | High — actively searching for solutions                           |
| Follow-up Needed?     | Any clarifications you still need             | Yes — unclear what "good enough quality" means to them            |

Fill in one row per participant. You'll complete this as you process each interview.

### Step 1.2 — Create a code book document

Open a separate document (Google Doc or text file). Title it "Code Book." Leave it empty for now. You will populate this during Phase 3. The code book is a living glossary of every tag/label you apply to interview data, with a definition for each one so your tagging stays consistent.

### Step 1.3 — Set up your clustering workspace

If physical: Get a large blank wall, a pad of sticky notes (ideally a few colors), and a marker.

If digital: Open a Miro or FigJam board. Create one large empty frame titled "Affinity Map — Raw Observations."

---

## Phase 2: Process Each Interview

**Repeat this for every interview. Do them in chronological order.**

### Step 2.1 — Generate a transcript

If you recorded audio/video, upload to your transcription tool and get a full text transcript. If you only have handwritten notes, type them up in full sentences, marking anything you're paraphrasing vs. quoting verbatim.

**Quality check:** Skim the transcript against the recording for the first 5 minutes. If the automated transcription has more than 1 error per paragraph, you need to do a manual correction pass. Names, jargon, and product names are almost always wrong in auto-transcription — fix those everywhere.

### Step 2.2 — Do a debrief dump (within 24 hours of the interview)

Before you even read the transcript carefully, write down your gut reactions from memory. Answer these five questions in 2-3 sentences each:

1. **What was the single most important thing this person told me?**
2. **What surprised me?**
3. **What confirmed something I already believed?** (Flag this — confirmation bias lives here.)
4. **Did this person contradict anything a previous participant said?**
5. **If I had to make one product decision based only on this interview, what would it be?**

Save this alongside the transcript. Label it "P[XX] Debrief Dump."

### Step 2.3 — Read and highlight the transcript

Read through the full transcript. As you read, highlight or bold the following types of content. Use a consistent color or marker for each type:

| Highlight color / marker         | What to highlight                                                | Example from transcript                                                           |
| -------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Yellow — Pain point              | Frustration, complaint, difficulty                               | "It takes me like 30 minutes every time to figure out why the eval score dropped" |
| Green — Behavior                 | Something they actually do (not hypothetical)                    | "I usually just grep through the logs and eyeball it"                             |
| Blue — Goal / desire             | What they're trying to achieve                                   | "I just want to know if my last code change broke anything for users"             |
| Pink — Emotion / strong reaction | Excitement, anger, resignation, surprise                         | "Honestly I've just given up on automated testing for this"                       |
| Orange — Quote                   | Particularly vivid or precise phrasing worth preserving verbatim | "It's like testing in the dark with oven mitts on"                                |

**Critical rule:** Only highlight what the participant actually said. Do not highlight your own questions, your reactions, or things they said in response to a leading prompt from you. If you asked "So you find it frustrating?" and they said "Yeah, I guess," that is not a strong data point.

### Step 2.4 — Update the master tracking spreadsheet

Go back to your master spreadsheet and fill in the row for this participant using the highlights you just created. Every cell should be grounded in something the participant said, not your interpretation.

---

## Phase 3: Code the Data

**Do this after you've processed at least 3 interviews. You can (and should) continue coding as you process more interviews.**

### Step 3.1 — Understand what "coding" means

Coding is the act of attaching a short descriptive label (a "code") to a segment of transcript text. The code describes the _topic or concept_ the person is talking about — not whether it's good or bad, not what you think about it.

**Examples of good codes:**

| Transcript segment                                                              | Code                      |
| ------------------------------------------------------------------------------- | ------------------------- |
| "I just run the whole test suite and hope for the best"                         | testing-workflow-manual   |
| "I don't know if my eval scores are actually measuring the right thing"         | eval-trust-validity       |
| "My co-founder keeps asking me if the AI feature is working and I can't answer" | stakeholder-reporting-gap |
| "I looked at Braintrust but it seemed like overkill for what I need"            | tool-evaluation-rejected  |

**Examples of bad codes:**

| Transcript segment                                      | Bad code      | Why it's bad                                                      |
| ------------------------------------------------------- | ------------- | ----------------------------------------------------------------- |
| "I just run the whole test suite and hope for the best" | problem       | Too vague — everything is a "problem"                             |
| "I looked at Braintrust but it seemed like overkill"    | braintrust    | Too specific to one brand — code the concept, not the proper noun |
| "I don't trust the scores"                              | user-is-wrong | You're injecting your judgment                                    |

### Step 3.2 — Do a first coding pass on your earliest interviews

Go through your first 3 highlighted transcripts. For each highlighted segment, write a code in the margin (if physical) or in a comment (if digital). Don't overthink it — you'll refine these later.

As you create new codes, add each one to your Code Book document with a one-sentence definition:

```md
Code Book (living document — update as you go)

testing-workflow-manual: Participant describes testing or quality-checking AI output by hand, without automation.
eval-trust-validity: Participant questions whether their evaluation metrics actually measure what matters.
stakeholder-reporting-gap: Participant cannot easily communicate AI product quality to non-technical stakeholders.
tool-evaluation-rejected: Participant evaluated a specific tool and chose not to adopt it.
onboarding-friction: Participant describes difficulty in initial setup or configuration of a tool.
time-cost-of-quality: Participant describes time spent on quality-related tasks as a significant burden.
```

### Step 3.3 — Stabilize your code book

After coding 3-4 interviews, review your Code Book. Look for:

- **Redundant codes:** "testing-manual" and "manual-testing-workflow" mean the same thing. Pick one, update all prior coding to match, and delete the other.
- **Codes that are too broad:** If "workflow-pain" has been applied to 15 different segments that are really about 4 different things, split it into more specific codes.
- **Codes that are too narrow:** If you have a code that only applies to one segment from one interview, it might be too specific. Consider merging it into a broader code.

**Target:** You want roughly 15-40 codes for a study of 6-12 interviews. Fewer than 15 means you're probably too broad. More than 40 means you're probably too granular.

### Step 3.4 — Finish coding all remaining interviews

Go through the rest of your transcripts, applying codes from your stabilized Code Book. When a segment doesn't fit any existing code, create a new one — but check the Code Book first to make sure you're not duplicating.

### Step 3.5 — Create a code-to-participant matrix

In your spreadsheet, create a new sheet/tab. List all your codes as rows and all participant IDs as columns. Put an "X" in each cell where that code appeared in that participant's interview.

| Code                      | P01 | P02 | P03 | P04 | P05 | P06 | P07 | P08 | Count |
| ------------------------- | --- | --- | --- | --- | --- | --- | --- | --- | ----- |
| testing-workflow-manual   | X   | X   |     | X   | X   |     | X   | X   | 6     |
| eval-trust-validity       | X   |     | X   | X   |     | X   |     | X   | 5     |
| stakeholder-reporting-gap |     |     | X   |     |     | X   | X   |     | 3     |
| tool-evaluation-rejected  | X   | X   |     |     | X   |     |     |     | 3     |
| onboarding-friction       |     | X   | X   |     | X   | X   |     |     | 4     |

The "Count" column tells you how widespread each code is. This is essential for separating signal from noise.

---

## Phase 4: Cluster Into Themes

**Do this after all interviews are coded.**

### Step 4.1 — Transfer codes to sticky notes

For each code in your Code Book, write one sticky note (physical or digital). On the sticky note, write:

- The code name
- The count (how many participants)
- One representative quote

Example sticky note:

```md
TESTING-WORKFLOW-MANUAL (6/8)
"I just grep through the logs and eyeball it"
```

### Step 4.2 — Do the affinity clustering

Lay out all sticky notes on your wall or digital board. Now physically move them into groups based on conceptual similarity. Follow these rules:

1. **Work silently if alone. If with a team, no talking during the first 15 minutes.** This prevents groupthink. Everyone clusters independently first.
2. **Move notes based on meaning, not surface-level words.** "eval-trust-validity" and "stakeholder-reporting-gap" might seem different, but if the underlying issue is "I can't prove quality to anyone including myself," they belong together.
3. **It's okay to have a note in no group.** Outliers are data too. Don't force everything into a cluster.
4. **If a cluster has more than 8 notes, it's probably two clusters.** Split it.
5. **If a cluster has only 1 note, it's not a theme — it's an observation.** Keep it separate; you'll handle it later.

### Step 4.3 — Name each cluster

Once your clusters feel stable, give each one a descriptive name. The name should describe the _user's experience_, not your product feature.

**Good theme names:**

- "Developers can't connect eval scores to specific product failures"
- "Quality assurance is treated as a manual, time-boxed chore"
- "Existing tools require too much setup to justify the effort"

**Bad theme names:**

- "Eval dashboards" (this is a feature, not a theme)
- "Pain points" (too vague)
- "Opportunity area 3" (meaningless)

### Step 4.4 — Validate cluster strength

For each theme, answer these three questions:

1. **Breadth:** How many participants contributed to this theme? Write it as a fraction (e.g., 6/8).
2. **Depth:** Are the data points within this theme surface-level mentions or deeply felt pain? Check for emotional language, behavioral evidence (things they actually do), and time/money costs they described.
3. **Consistency:** Do the data points within this theme say the same thing, or are there internal contradictions?

Record this in a table:

| Theme                                      | Breadth | Depth                                                        | Consistency                                               | Confidence |
| ------------------------------------------ | ------- | ------------------------------------------------------------ | --------------------------------------------------------- | ---------- |
| Can't connect scores to failures           | 6/8     | High — multiple described specific failed debugging sessions | Strong — no contradictions                                | HIGH       |
| Quality assurance is manual and time-boxed | 5/8     | Medium — mentioned as annoyance, but most have accepted it   | Moderate — two participants actually prefer manual review | MEDIUM     |
| Existing tools require too much setup      | 3/8     | Low — only evaluated tools briefly before dismissing them    | Weak — different tools, different reasons                 | LOW        |

**Confidence rating guide:**

- **HIGH:** 5+ participants, deep/emotional data, no contradictions. Safe to build on.
- **MEDIUM:** 3-4 participants, moderate depth, minor contradictions. Worth exploring further.
- **LOW:** 1-2 participants, or shallow mentions, or internal contradictions. Do not make product decisions based on this alone.

---

## Phase 5: Extract Insights

**This is the hardest and most important phase. Do not rush it.**

### Step 5.1 — Understand the difference between observations and insights

|             | Observation                                          | Insight                                                                                                                                                                                      |
| ----------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition  | A factual statement about what you saw in the data   | An interpretive conclusion about why you saw it and what it means                                                                                                                            |
| Example     | "6 of 8 participants manually spot-check AI outputs" | "Developers resort to manual spot-checking because existing automated eval tools don't let them trace a failure back to a root cause — they need explainability, not just a pass/fail score" |
| Actionable? | No — it tells you what, not what to do about it      | Yes — it suggests a specific product direction                                                                                                                                               |
| Testable?   | Not directly                                         | Yes — you can validate whether providing root-cause tracing actually reduces manual spot-checking                                                                                            |

### Step 5.2 — Draft insights from each HIGH and MEDIUM confidence theme

For each theme rated HIGH or MEDIUM confidence, write an insight statement using this template:

```md
INSIGHT TEMPLATE:

[User group] does [observed behavior]
because [underlying reason/motivation].
This matters because [consequence/implication].
This suggests we should [potential action].

SUPPORTING EVIDENCE:

- [Participant ID]: "[verbatim quote]"
- [Participant ID]: "[verbatim quote]"
- [Participant ID]: [behavioral observation]
  (minimum 3 data points per insight)
```

**Example:**

```md
INSIGHT:

Solo developers building LLM features rely on manual, ad-hoc quality checks
(grep through logs, eyeball 10 random outputs) because existing eval
frameworks require significant setup investment with unclear payoff.
This matters because the manual approach doesn't scale — quality regressions
ship to users undetected until customer complaints surface.
This suggests we should provide an eval workflow that requires zero
configuration and produces results within the first 5 minutes of use.

SUPPORTING EVIDENCE:

- P01: "I just grep through the logs and eyeball it, maybe 10 outputs"
- P04: "I looked at Braintrust, set up took like 2 hours and I still didn't
  know if the scores meant anything"
- P05: "I found out about the bug from a user tweet, not from any test"
- P07: Had a regression live for 3 weeks before a customer reported it
- P08: "If it takes more than 10 minutes to set up I'm probably not going
  to do it"
```

### Step 5.3 — Stress-test each insight

For every insight you've drafted, run it through these five challenges:

1. **The "so what" test:** If a product manager read this insight and said "so what should I build?", could you give a clear answer? If not, the insight is too vague.

2. **The disconfirming evidence check:** Go back to your transcripts and actively look for data points that _contradict_ this insight. Did any participant say the opposite? If yes, note it and either revise the insight or document the contradiction as a segment boundary.

3. **The "is this actually two insights?" check:** If your insight statement has the word "and" connecting two distinct ideas, it might be two separate insights. Split them.

4. **The attribution check:** Is this insight grounded in what participants _actually said and did_, or is it your own speculation? Every clause in the insight should be traceable to specific transcript data.

5. **The "would this be true even without our interviews?" test:** If the insight is something anyone could have guessed without talking to users (e.g., "developers prefer simple tools"), it's too generic. Push deeper into the specific, non-obvious aspects.

### Step 5.4 — Rank insights by impact and confidence

Create a 2x2 matrix:

```md
                        HIGH CONFIDENCE
                              |
                              |
     IMPORTANT BUT       ★ ACT ON THESE ★
     NEEDS MORE DATA          |
                              |

─────────────── LOW IMPACT ─┼─ HIGH IMPACT ──────────
|
PARK THESE | WATCH THESE
(nice to know) | (intriguing but unvalidated)
|
LOW CONFIDENCE
```

Place each insight on this matrix. Your top-right quadrant (high confidence + high impact) is where product decisions should come from.

---

## Phase 6: Identify Segments and Contradictions

### Step 6.1 — Look for natural participant groupings

Review your code-to-participant matrix from Step 3.5. Do certain participants cluster together — sharing many of the same codes while differing from other participants? If so, you may have distinct user segments.

Mark potential segments in your master spreadsheet by adding a "Segment" column:

| Participant        | Segment            | Defining characteristic                                            |
| ------------------ | ------------------ | ------------------------------------------------------------------ |
| P01, P04, P05, P08 | "Flying blind"     | No automated quality process at all; ships and prays               |
| P02, P06           | "Manual inspector" | Has a quality process, but it's entirely manual and time-consuming |
| P03, P07           | "Tool-frustrated"  | Tried one or more tools, couldn't get value, reverted to manual    |

### Step 6.2 — Check if contradictions are actually segment boundaries

When two participants say opposite things, check if they belong to different segments. Contradictions between segments are expected and informative — they tell you that your product may need different value propositions for different users.

**Example:**

- P02 says: "I actually like doing manual review — it keeps me close to the quality."
- P05 says: "Manual review is a total waste of my time."
- This isn't confusing noise — P02 is a "manual inspector" who values the control. P05 is "flying blind" and resents that they _have_ to do it. Different segments, different attitudes toward the same behavior.

### Step 6.3 — Document say/do gaps

Review each participant for discrepancies between what they _said_ they do and what their _actual behavior_ reveals. Common patterns:

| What they said                            | What they actually do                                     | What this means                                                                                                        |
| ----------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| "Quality is my top priority"              | Spends less than 5 minutes on QA per release              | Quality is aspirational, not practiced. They need a solution that requires near-zero effort.                           |
| "I'd definitely pay for a tool like this" | Has evaluated and rejected 3 similar tools                | Stated willingness to pay does not predict adoption. Ease of setup is the real gate.                                   |
| "I test everything before I ship"         | Described a process that only covers happy-path scenarios | They think they test thoroughly, but they have blind spots. They need to discover edge cases they didn't know existed. |

---

## Phase 7: Create Synthesis Artifacts

### Step 7.1 — Write the one-page insight summary

This is the most important deliverable. It should fit on a single page (or a single screen) and be readable in 3 minutes. Use this structure:

```md
═══════════════════════════════════════════════
RESEARCH SUMMARY: [Study Name]
[Date] | [# of interviews] | [Participant profile]
═══════════════════════════════════════════════

RESEARCH QUESTIONS:
What were we trying to learn?

KEY INSIGHTS (ranked by confidence × impact):

1. [Insight statement — one paragraph]
   Evidence: [X/N participants]. Representative quote.

2. [Insight statement — one paragraph]
   Evidence: [X/N participants]. Representative quote.

3. [Insight statement — one paragraph]
   Evidence: [X/N participants]. Representative quote.

SEGMENTS IDENTIFIED:

- [Segment A]: [one sentence description] ([n] participants)
- [Segment B]: [one sentence description] ([n] participants)

OPEN QUESTIONS:
Things we still don't know and should investigate.

RECOMMENDED NEXT STEPS:
What should we do based on these findings?
```

### Step 7.2 — Build supporting evidence documents (optional but valuable)

If your stakeholders will want to dig deeper, prepare these supplementary artifacts:

**A. Theme-level evidence sheets** — One page per theme, containing every relevant quote and behavioral observation from every participant, organized by participant ID. This lets anyone trace an insight back to the raw data.

**B. Participant profiles** — One paragraph per participant summarizing their context, key quotes, and which themes they contributed to. Use participant IDs, not real names.

**C. Prioritized pain point list** — A ranked list of user pain points with breadth (how many participants mentioned it), depth (how strongly they felt it), and current workaround (how they cope today).

| Rank | Pain point                                        | Breadth | Depth  | Current workaround    |
| ---- | ------------------------------------------------- | ------- | ------ | --------------------- |
| 1    | Cannot trace eval failures to root cause          | 6/8     | High   | Manual log inspection |
| 2    | Setup cost of eval tools is prohibitive           | 5/8     | Medium | Avoid tools entirely  |
| 3    | Cannot communicate quality status to stakeholders | 3/8     | High   | Anecdotal reports     |

### Step 7.3 — Prepare presentation-ready findings (if needed)

If you need to present to a team or stakeholders, structure your presentation as:

1. **Reminder of research goals** (1 slide / 30 seconds)
2. **Who we talked to** — participant demographics, _not_ individual identities (1 slide / 1 minute)
3. **Top 3 insights with quotes** — one slide per insight, each with a key quote that makes it feel real (3 slides / 5 minutes)
4. **Segments discovered** (1 slide / 2 minutes)
5. **What we should do next** — specific, concrete actions (1 slide / 2 minutes)

Total: about 10 minutes of presentation time. Resist adding more slides. If people want to dig deeper, point them to the evidence documents.

---

## Phase 8: Validate and Iterate

### Step 8.1 — Peer debrief (if you have collaborators)

Walk a colleague through your raw data (codes, clusters, quotes) _without_ showing your insights. Ask them what conclusions they draw. If they arrive at similar insights independently, your synthesis is strong. If they see something completely different, revisit your clustering.

### Step 8.2 — Member check (optional but powerful)

Share a brief summary of your findings (without attributing anything to specific participants) with 1-2 of your interview participants. Ask: "Does this ring true to your experience?" This is not about getting their approval — it's about catching cases where you fundamentally misunderstood something.

### Step 8.3 — Document what you'd do differently

After every study, write a brief retrospective (3-5 bullet points):

- Which interview questions produced the richest data?
- Which questions fell flat?
- Were there topics that kept coming up that you didn't have questions for?
- Did you have the right participant mix, or were you missing a segment?
- What would you change about your interview guide for the next round?

This retrospective is your most valuable asset for improving your research practice over time.

---

## Quick Reference: Common Mistakes Checklist

Before you finalize your synthesis, check yourself against these failure modes:

- [ ] **Confirmation bias:** Did I actively look for data that contradicts my insights?
- [ ] **Single-participant themes:** Am I treating something one person said as a broadly-held truth?
- [ ] **Feature-solution framing:** Are my themes about the user's experience, or about my product ideas?
- [ ] **Quote cherry-picking:** Am I only using quotes that support my preferred narrative?
- [ ] **Missing segments:** Did I check for contradictions that might indicate distinct user groups?
- [ ] **Say/do gaps:** Did I compare stated preferences against actual behaviors?
- [ ] **Vague insights:** Could someone read each insight and know what to build or not build?
- [ ] **Orphan data:** Is there significant data I coded but never clustered? Why?
- [ ] **Over-interpretation:** Are my insights supported by 3+ data points, or am I speculating?
- [ ] **Recency bias:** Am I giving too much weight to the last few interviews just because they're freshest in memory?

---

## Appendix: Glossary

| Term             | Definition                                                                                                     |
| ---------------- | -------------------------------------------------------------------------------------------------------------- |
| Code             | A short label applied to a segment of transcript to describe what topic or concept is being discussed          |
| Code book        | A document listing all codes with definitions, maintained as a living reference throughout synthesis           |
| Affinity diagram | A spatial clustering technique where individual data points are physically grouped by conceptual similarity    |
| Theme            | A higher-level grouping of related codes that represents a recurring pattern across multiple participants      |
| Observation      | A factual statement about what was seen in the data (e.g., "5/8 participants do X")                            |
| Insight          | An interpretive conclusion that explains why the observation exists and what it implies for decisions          |
| Say/do gap       | A discrepancy between what a participant claims to do and what their actual behavior reveals                   |
| Member check     | Sharing findings with participants to verify the researcher's interpretation matches their experience          |
| Segment          | A distinct group of participants who share similar characteristics, behaviors, or needs                        |
| Breadth          | How many participants a given theme or code appears across (e.g., 6/8)                                         |
| Depth            | How strongly or emotionally participants feel about a given theme — surface-level mention vs. deeply felt pain |
| Deductive coding | Starting with a predefined set of codes based on your research questions, then applying them to data           |
| Inductive coding | Letting codes emerge naturally from the data as you read through transcripts                                   |
