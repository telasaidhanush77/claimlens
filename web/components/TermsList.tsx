"use client";

import { useState } from "react";
import { rupees } from "@/lib/api";
import { CATEGORY_LABEL, type Limit, type PolicyTerms, type Term, type TermName } from "@/lib/types";

const LABEL: Record<TermName, string> = {
  sum_insured: "Sum insured",
  room_limit: "Room rent limit",
  icu_limit: "ICU limit",
  proportionate: "Proportionate deduction",
  proportionate_categories: "…applies to",
  copay_pct: "Co-pay",
  deductible: "Deductible",
  sublimits: "Procedure sub-limits",
  non_payable: "Never paid",
};

// Terms a person can reasonably type in when the policy reader couldn't prove them.
const EDITABLE: TermName[] = ["sum_insured", "room_limit", "icu_limit", "proportionate", "copay_pct", "deductible"];

function show(name: TermName, t: Term<unknown>, si: Term<unknown>): string {
  const v = t.value as never;
  if (v === null) return "";
  switch (name) {
    case "sum_insured":
    case "deductible":
      return Number(v) === 0 ? "None" : rupees(v);
    case "copay_pct":
      return Number(v) === 0 ? "None" : `${Number(v)}%`;
    case "room_limit":
    case "icu_limit": {
      const l = v as Limit;
      if (l.kind === "per_day") return `${rupees(l.amount)} per day`;
      const perDay = si.value ? ` (${rupees((Number(si.value) * Number(l.amount)) / 100)}/day)` : "";
      return `${Number(l.amount)}% of sum insured per day${perDay}`;
    }
    case "proportionate":
      return v ? "Yes" : "No";
    case "proportionate_categories":
    case "non_payable":
      return (v as string[]).map((c) => CATEGORY_LABEL[c as keyof typeof CATEGORY_LABEL] ?? c).join(", ") || "None";
    case "sublimits":
      return Object.entries(v as Record<string, string>).map(([k, a]) => `${k} ${rupees(a)}`).join(" · ") || "None";
  }
}

type Props = { terms: PolicyTerms; onSave: (terms: PolicyTerms) => Promise<void> };

export function TermsList({ terms, onSave }: Props) {
  return (
    <ul className="divide-y divide-line rounded-xl border border-line bg-card">
      {(Object.keys(LABEL) as TermName[]).map((name) => (
        <TermRow key={name} name={name} terms={terms} onSave={onSave} />
      ))}
    </ul>
  );
}

function TermRow({ name, terms, onSave }: { name: TermName } & Props) {
  const t = terms[name] as Term<unknown>;
  const entered = !t.verified && t.value !== null;
  return (
    <li className="grid gap-1 px-4 py-3 sm:grid-cols-[12rem_1fr] sm:gap-4">
      <span className="text-sm font-medium text-muted">{LABEL[name]}</span>
      <div className="min-w-0">
        {t.value !== null ? (
          <p className="num font-medium">
            {show(name, t, terms.sum_insured)}
            {t.verified && (
              <span className="ml-2 rounded-full bg-teal-soft px-2 py-0.5 text-xs font-medium text-teal">✓ quoted p.{t.page}</span>
            )}
            {entered && <span className="ml-2 text-xs text-muted">entered by you</span>}
          </p>
        ) : EDITABLE.includes(name) ? (
          <TermInput name={name} terms={terms} onSave={onSave} />
        ) : (
          <p className="text-sm text-muted">Not found in the policy, treated as none.</p>
        )}
        {t.verified && t.quote && (
          <blockquote className="mt-1 border-l-2 border-line pl-3 font-serif text-sm italic text-muted">“{t.quote}”</blockquote>
        )}
      </div>
    </li>
  );
}

function TermInput({ name, terms, onSave }: { name: TermName } & Props) {
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<Limit["kind"]>("per_day");
  const [saving, setSaving] = useState(false);
  const isLimit = name === "room_limit" || name === "icu_limit";
  const isBool = name === "proportionate";

  const save = async (raw: string) => {
    if (raw === "") return;
    const value = isBool ? raw === "yes" : isLimit ? { kind, amount: raw } : raw;
    setSaving(true);
    try {
      await onSave({ ...terms, [name]: { value, page: null, quote: null, verified: false } });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg bg-amber-soft px-3 py-2 text-sm">
      <span className="text-amber">Not found in your policy. Enter it from your policy schedule:</span>
      {isBool ? (
        <select aria-label={LABEL[name]} disabled={saving} defaultValue="" onChange={(e) => save(e.target.value)} className="rounded border border-line px-2 py-1">
          <option value="" disabled>Choose</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      ) : (
        <>
          <input
            aria-label={LABEL[name]} inputMode="decimal" disabled={saving} value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
            onBlur={() => save(amount)} onKeyDown={(e) => e.key === "Enter" && save(amount)}
            className="num w-28 rounded border border-line px-2 py-1"
            placeholder={name === "copay_pct" ? "%" : "₹"}
          />
          {isLimit && (
            <select aria-label="Limit type" value={kind} onChange={(e) => setKind(e.target.value as Limit["kind"])} className="rounded border border-line px-2 py-1">
              <option value="per_day">₹ per day</option>
              <option value="pct_si">% of sum insured</option>
            </select>
          )}
        </>
      )}
    </div>
  );
}
