import { rupees } from "@/lib/api";
import type { Simulation } from "@/lib/types";

export function ResultView({ sim, roomRate }: { sim: Simulation; roomRate: number | null }) {
  const share = sim.billed ? (sim.insurer_pays / sim.billed) * 100 : 0;
  const current = sim.room_choices.find((c) => Number(c.rate_per_day) === roomRate);
  const best = sim.room_choices[0];
  const saving = current && best && best.name !== current.name ? current.you_pay - best.you_pay : 0;

  return (
    <div className="space-y-8">
      <div className="rounded-2xl border border-line bg-card p-6 shadow-[0_1px_0_#e2dacb,0_12px_32px_-20px_#1d1b1833]">
        <div className="grid gap-6 sm:grid-cols-2">
          <Figure label="Insurer pays" value={sim.insurer_pays} tone="text-teal" />
          <Figure label="You pay" value={sim.you_pay} tone="text-loss" />
        </div>
        <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-[#f1d9d4]" role="img" aria-label={`Insurer covers ${share.toFixed(0)}% of the bill`}>
          <div className="h-full rounded-full bg-teal" style={{ width: `${share}%` }} />
        </div>
        <p className="num mt-2 text-sm text-muted">Hospital bill {rupees(sim.billed)} · insurer covers {share.toFixed(0)}%</p>
        <p className="mt-4 text-xs text-muted">Estimate only, not insurance advice. Check the quoted clauses.</p>
      </div>

      {saving > 0 && (
        <div className="rounded-xl bg-teal-soft p-4 text-sm">
          <span className="font-medium">Choose {best.name.toLowerCase()} and you pay {rupees(saving)} less.</span>{" "}
          Your room costs more than the policy&apos;s daily limit, so the insurer cuts other charges too.
        </div>
      )}

      {sim.room_choices.length > 0 && (
        <section>
          <h3 className="font-serif text-xl">If you pick a different room</h3>
          <ol className="mt-3 divide-y divide-line rounded-xl border border-line bg-card">
            {sim.room_choices.map((c, i) => (
              <li key={c.name} className="num flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 text-sm">
                <span className="font-medium">{i === 0 && <span className="mr-2 text-teal">★</span>}{c.name} <span className="font-normal text-muted">{rupees(c.rate_per_day)}/day</span></span>
                <span>you pay <strong>{rupees(c.you_pay)}</strong></span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section>
        <h3 className="font-serif text-xl">Line by line</h3>
        <div className="relative mt-3 overflow-x-auto rounded-xl border border-line bg-card">
          <table className="num w-full min-w-[34rem] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted">
              <tr><th className="p-3">Item</th><th className="p-3 text-right">Billed</th><th className="p-3 text-right">Insurer pays</th><th className="p-3">Why</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sim.lines.map((l, i) => (
                <tr key={`${l.description}-${i}`} className="align-top">
                  <td className="p-3">{l.description}</td>
                  <td className="p-3 text-right">{rupees(l.billed)}</td>
                  <td className={`p-3 text-right ${Number(l.payable) < Number(l.billed) ? "text-loss" : ""}`}>{rupees(l.payable)}</td>
                  <td className="p-3 text-muted">{l.notes.join(" · ") || "Paid in full"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h3 className="font-serif text-xl">How the claim was worked out</h3>
        <ol className="num mt-3 space-y-1 text-sm">
          {sim.steps.map((s, i) => (
            <li key={`${s.label}-${i}`} className="flex justify-between gap-4 border-b border-dashed border-line py-1.5">
              <span>{s.label}{s.page && <span className="ml-2 text-xs text-muted">p.{s.page}</span>}</span>
              <span>{rupees(s.total_after)}</span>
            </li>
          ))}
          <li className="flex justify-between gap-4 py-1.5 font-semibold"><span>Insurer pays</span><span>{rupees(sim.insurer_pays)}</span></li>
        </ol>
      </section>
    </div>
  );
}

function Figure({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div>
      <p className="text-sm text-muted">{label}</p>
      <p className={`num font-serif text-5xl tracking-tight ${tone}`}>{rupees(value)}</p>
    </div>
  );
}
