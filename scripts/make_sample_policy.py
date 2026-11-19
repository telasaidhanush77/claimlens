"""Writes app/sample/policy.pdf: a FICTIONAL policy wording in the style of an Indian
health-insurance policy, so the demo needs no real insurer's document."""

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "app" / "sample" / "policy.pdf"
TITLE = "ClaimLens Sample Health Policy (fictional)"
FOOTER = "Fictional document for demonstration. Not issued by any insurer."

PAGES = [
    ("Part A - Preamble and Definitions", [
        "This Policy is a contract between the Insured Person and the Company. Hospitalisation "
        "expenses incurred during the Policy Period are payable subject to the terms, "
        "conditions, limits and exclusions in this Policy wording.",
        "1.1 Hospital means an institution registered with the local authorities, with at "
        "least 10 in-patient beds, qualified nursing staff round the clock and a fully "
        "equipped operation theatre.",
        "1.2 Associated Medical Expenses means surgeon and consultant fees, operation theatre "
        "charges, diagnostic and investigation charges, and other hospital charges that vary "
        "with the room category chosen.",
        "1.3 Room Category means the class of accommodation (general ward, twin sharing, "
        "single private room, deluxe room) occupied by the Insured Person.",
    ]),
    ("Part B - Sum Insured and Coverage", [
        "2.1 The Sum Insured under this Policy is Rs. 5,00,000 for each Policy Year, "
        "available on a floater basis to all Insured Persons.",
        "2.2 The Company will pay the Medically Necessary expenses of In-patient "
        "Hospitalisation for a minimum period of 24 consecutive hours.",
        "2.3 Pre-hospitalisation expenses for 30 days and post-hospitalisation expenses for "
        "60 days are payable, subject to the claim for hospitalisation being admissible.",
    ]),
    ("Part C - Limits on Room, ICU and Associated Expenses", [
        "3.1 Room rent, boarding and nursing expenses are payable up to 1% of the Sum Insured "
        "per day for a normal room.",
        "3.2 Intensive Care Unit (ICU) charges are payable up to 2% of the Sum Insured per day.",
        "3.3 Proportionate deduction: if the Insured Person occupies a room whose rent exceeds "
        "the limit in Clause 3.1, the Associated Medical Expenses (surgeon and consultant "
        "fees, operation theatre charges, diagnostic charges and other hospital charges) shall "
        "be payable in the same proportion as the admissible room rent bears to the actual "
        "room rent.",
        "3.4 The proportionate deduction in Clause 3.3 shall not apply to the cost of "
        "medicines, implants and consumables.",
    ]),
    ("Part D - Co-payment and Sub-limits", [
        "4.1 A co-payment of 10% shall apply to every admissible claim under this Policy, "
        "after all other limits have been applied.",
        "4.2 The following sub-limits apply per Policy Year: Cataract surgery up to "
        "Rs. 40,000 per eye; Knee replacement up to Rs. 3,00,000.",
        "4.3 No deductible applies under this Policy.",
    ]),
    ("Part E - Exclusions", [
        "5.1 Expenses for cosmetic or plastic surgery, unless needed after an accident, are "
        "excluded.",
        "5.2 Dental treatment, spectacles and contact lenses are excluded unless arising from "
        "hospitalisation for an accident.",
        "5.3 Expenses attributable to self-inflicted injury are excluded.",
    ]),
    ("Annexure I - List of Non-payable Items", [
        "Consumables are not payable under this Policy. These include gloves, masks, syringes, "
        "cotton, gauze, disposable linen, caps, and similar items listed by the regulator.",
        "Administrative charges such as registration fees, admission kits and documentation "
        "charges are also not payable.",
    ]),
]


class Doc(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 8, TITLE, align="R")
        self.ln(12)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"{FOOTER}  Page {self.page_no()}", align="C")


def main() -> None:
    doc = Doc()
    for heading, paragraphs in PAGES:
        doc.add_page()
        doc.set_font("Helvetica", "B", 13)
        doc.multi_cell(0, 8, heading)
        doc.ln(3)
        doc.set_font("Helvetica", size=11)
        for p in paragraphs:
            doc.multi_cell(0, 6, p)
            doc.ln(3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.output(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
