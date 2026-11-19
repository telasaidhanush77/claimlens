# ClaimLens: design

## Intent

Patients in India find out what their health insurance will pay *after* discharge. The free
"claim calculators" online make you type your own policy limits and guess how the rules
apply. Some of them say so outright: they won't apply a room-rent deduction unless you
confirm your policy wording allows it. The answer is in the policy document, and none of
these tools reads it.

ClaimLens reads it. You upload your policy wording PDF and the hospital's cost estimate
*before* admission. You get:

1. the clauses that decide your claim (room-rent limit, ICU limit, co-pay, procedure
   sub-limits, deductible, non-payable items), each one **quoted with its page number**;
2. a line-by-line claim simulation: insurer pays X, you pay Y, and the reason for every rupee;
3. cheaper choices, e.g. "a twin-sharing room cuts what you pay from ₹42,000 to ₹6,000";
4. (stage 2) when a claim is rejected or cut, an appeal letter drafted from the rejection
   letter and the policy. A human approves it before it is final.

## Goals

- **Never invent a rupee.** The LLM only *finds and quotes* clauses. Plain Python does all
  the arithmetic. Every quote is checked against the PDF text; a quote that isn't in the
  document is rejected and that term is marked "not found, enter it yourself".
- Works on real Indian policy wordings, not only on the bundled sample.
- One live URL, and a reproducible benchmark behind every accuracy claim.

## Non-goals

- Not insurance or legal advice. Every result says so, and links the exact clause.
- No sending: the appeal is a letter the user downloads. Nothing is filed for them.
- No accounts or logins. No payment.
- Not a general medical-bill OCR system. Stage 1 estimates are entered as line items
  (form or CSV); reading estimate PDFs is a later stage if time allows.

## Anti-goals (failure even if it "works")

- A number on screen that the code can't explain line by line.
- A clause citation that isn't actually in the document.
- Any real patient data. Bills are synthetic; policies are public documents.

## Constraints

- Free tiers only: Render (web), Neon (Postgres + pgvector), Gemini / Groq APIs.
- Each insurer words the same rule differently. The proportionate-deduction rule in
  particular varies: which charges it touches, and whether it applies at all.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | LLM reads the policy and directly answers "how much will I pay" | Fast to build, but numbers can't be checked and will sometimes be wrong. Rejected (anti-goal 1). |
| **B (chosen)** | LLM extracts a typed set of policy terms with verified quotes; a deterministic engine computes the claim | Every rupee is explainable and testable. Costs a schema for terms. |
| C | No LLM: regex over policy text | Breaks on varied insurer wording; doesn't scale beyond one insurer. |

## Design

**Stack.** Next.js (TypeScript, static export) front end served by a Python FastAPI back
end from one Docker image, so there is one URL. Postgres with pgvector. Deployed on
Render + Neon.

**Flow.**

```
policy PDF ─► pages (pypdf) ─► chunks + embeddings (pgvector)
                                   │
          for each term: retrieve top chunks ─► LLM → {value, page, quote}
                                   │
                    verify quote is on that page ─► PolicyTerms (typed)
                                                        │
hospital estimate (line items) ──────────────► claim engine (pure Python)
                                                        │
                                  per-line breakdown + room-choice comparison
```

**Policy terms (typed).** sum insured; room-rent limit (₹/day or % of sum insured, by room
category); ICU limit; proportionate deduction (applies? to which charge categories?);
co-pay %; deductible; procedure sub-limits; non-payable item categories. Each term carries
`value`, `page`, `quote`, `verified`.

**Claim engine.** Pure functions, no I/O. Estimate line items have a category (room, ICU,
surgeon, OT, diagnostics, medicines, consumables, implants, other). Order of application:
non-payables → room/ICU excess → proportionate deduction on the categories the policy
names → sub-limits → deductible → co-pay → sum-insured cap. Each step writes an
explanation line. A "what if" runs the engine once per room category.

**Appeal agent (stage 2).** LangGraph graph with tools: search the policy, read the
simulation, quote a clause. It drafts, then pauses at a human-approval step. The paused
state is saved in Postgres, so approval can come later from another request. Edit,
approve, or reject; an approved letter downloads as a PDF/text file.

**Demo mode.** LLM answers for the bundled sample policy are cached, so the live demo
works without API quota and gives the same output every time.

**Benchmark.** Hand-label the key terms of a handful of public policy wordings, then
measure extraction accuracy and the share of rejected (unverifiable) quotes per model.
The README table is written by the benchmark script.

## Stages

1. Policy reader + verified extraction + claim engine + room comparison, deployed.
2. Appeal agent with human approval.
3. Benchmark on real policy wordings; README results.

## Left to the builder

Exact term schema field names, chunk size, prompt wording, UI layout and styling, choice of
embedding model, which public policy wordings go in the benchmark.
