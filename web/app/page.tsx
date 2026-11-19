"use client";

import { useState } from "react";
import { draftFrom, estimateFrom, EstimateEditor, type Draft } from "@/components/EstimateEditor";
import { PolicyStep } from "@/components/PolicyStep";
import { ResultView } from "@/components/ResultView";
import { TermsList } from "@/components/TermsList";
import { api } from "@/lib/api";
import type { Policy, PolicyTerms, Simulation } from "@/lib/types";

const EMPTY: Draft = { procedure: "", items: [], rooms: [] };

export default function Home() {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [sim, setSim] = useState<Simulation | null>(null);
  const [busy, setBusy] = useState<"" | "policy" | "estimate" | "simulate">("");
  const [error, setError] = useState("");

  async function run<T>(kind: typeof busy, task: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError("");
    try {
      return await task();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy("");
    }
  }

  const loadPolicy = async (task: () => Promise<Policy>) => {
    const p = await run("policy", task);
    if (p) { setPolicy(p); setSim(null); }
  };
  const saveTerms = async (terms: PolicyTerms) => {
    if (!policy) return;
    const p = await run("policy", () => api.saveTerms(policy.id, terms));
    if (p) { setPolicy(p); setSim(null); }
  };
  const loadSampleEstimate = async () => {
    const est = await run("estimate", api.sampleEstimate);
    if (est) { setDraft(draftFrom(est)); setSim(null); }
  };
  const calculate = async () => {
    if (!policy) return;
    const s = await run("simulate", () => api.simulate(policy.id, estimateFrom(draft)));
    if (s) setSim(s);
  };

  const room = draft.items.find((i) => i.category === "room" && i.days);
  const roomRate = room ? Number(room.amount) / Number(room.days) : null;

  return (
    <main className="mx-auto max-w-4xl px-4 pb-24 pt-10 sm:px-6 sm:pt-16">
      <header className="max-w-2xl">
        <p className="text-sm font-medium uppercase tracking-[0.18em] text-teal">ClaimLens</p>
        <h1 className="mt-3 font-serif text-4xl leading-tight sm:text-5xl">
          Know what your health insurance will pay <em>before</em> you&apos;re admitted.
        </h1>
        <p className="mt-4 text-muted">
          Upload your policy wording and the hospital&apos;s estimate. ClaimLens reads the rules that decide your claim,
          quotes each one with its page, and works out your bill line by line. The AI only finds the clauses; every
          rupee is calculated by plain, checkable code.
        </p>
      </header>

      {error && (
        <p role="alert" className="mt-8 rounded-lg border border-[#e7b9b0] bg-[#fbecea] px-4 py-3 text-sm text-loss">{error}</p>
      )}

      <Section n={1} title="Your policy">
        <PolicyStep busy={busy !== ""} onUpload={(f) => loadPolicy(() => api.uploadPolicy(f))} onSample={() => loadPolicy(api.samplePolicy)} />
        {busy === "policy" && <p className="mt-3 text-sm text-muted" aria-live="polite">Reading your policy… about 20 seconds.</p>}
      </Section>

      {policy && (
        <>
          <Section n={2} title="What your policy says" note={policy.name}>
            <TermsList terms={policy.terms} onSave={saveTerms} />
          </Section>

          <Section n={3} title="The hospital's estimate">
            {draft.items.length === 0 ? (
              <div className="flex flex-wrap gap-3">
                <button type="button" onClick={loadSampleEstimate} disabled={busy !== ""} className="rounded-lg bg-ink px-5 py-3 font-medium text-paper hover:bg-teal disabled:opacity-60">
                  Load sample estimate (knee replacement)
                </button>
                <button type="button" onClick={() => setDraft({ ...EMPTY, items: draftFrom({ procedure: null, items: [{ description: "Room", category: "room", amount: "", days: 1 }], room_options: [] }).items })} className="rounded-lg border border-line px-5 py-3 font-medium hover:border-teal">
                  Enter my own
                </button>
              </div>
            ) : (
              <>
                <EstimateEditor draft={draft} onChange={(d) => { setDraft(d); setSim(null); }} />
                <button type="button" onClick={calculate} disabled={busy !== ""} className="mt-6 rounded-lg bg-teal px-6 py-3 font-medium text-white hover:bg-ink disabled:opacity-60">
                  {busy === "simulate" ? "Working it out…" : "Work out my claim"}
                </button>
              </>
            )}
          </Section>
        </>
      )}

      {sim && (
        <Section n={4} title="Your claim">
          <ResultView sim={sim} roomRate={roomRate} />
        </Section>
      )}

      <footer className="mt-20 border-t border-line pt-6 text-xs text-muted">
        ClaimLens is a portfolio project. It estimates; it does not decide claims. The sample policy is fictional.
      </footer>
    </main>
  );
}

function Section({ n, title, note, children }: { n: number; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="mt-14">
      <div className="mb-4 flex items-baseline gap-3">
        <span className="num font-serif text-2xl text-teal">{n}</span>
        <h2 className="font-serif text-2xl">{title}</h2>
        {note && <span className="truncate text-sm text-muted">{note}</span>}
      </div>
      {children}
    </section>
  );
}
