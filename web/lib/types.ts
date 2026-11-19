// Mirrors app/models.py. Decimals arrive as strings from the API.
export type Money = string | number;

export const CATEGORIES = [
  "room", "icu", "surgeon", "ot", "diagnostics", "medicines", "consumables", "implants", "other",
] as const;
export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<Category, string> = {
  room: "Room rent", icu: "ICU", surgeon: "Surgeon / doctor fees", ot: "Operation theatre",
  diagnostics: "Diagnostics", medicines: "Medicines", consumables: "Consumables",
  implants: "Implants", other: "Other hospital charges",
};

export type Term<T> = { value: T | null; page: number | null; quote: string | null; verified: boolean };
export type Limit = { kind: "per_day" | "pct_si"; amount: Money };

export type PolicyTerms = {
  sum_insured: Term<Money>;
  room_limit: Term<Limit>;
  icu_limit: Term<Limit>;
  proportionate: Term<boolean>;
  proportionate_categories: Term<Category[]>;
  copay_pct: Term<Money>;
  deductible: Term<Money>;
  sublimits: Term<Record<string, Money>>;
  non_payable: Term<Category[]>;
};
export type TermName = keyof PolicyTerms;

export type Policy = { id: string; name: string; terms: PolicyTerms };

export type LineItem = { description: string; category: Category; amount: Money; days: number | null };
export type RoomOption = { name: string; rate_per_day: Money };
export type Estimate = { procedure: string | null; items: LineItem[]; room_options: RoomOption[] };

export type LineResult = { description: string; category: Category; billed: Money; payable: Money; notes: string[] };
export type Step = { label: string; total_after: Money; page: number | null };
export type RoomChoice = { name: string; rate_per_day: Money; insurer_pays: number; you_pay: number };
export type Simulation = {
  lines: LineResult[]; steps: Step[]; billed: number; insurer_pays: number; you_pay: number;
  room_choices: RoomChoice[];
};
