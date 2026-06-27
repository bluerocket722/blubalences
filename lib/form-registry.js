//
// form-registry.js — Detects which government form a PDF is, with no network
// and no external service (EU-sovereign). Detection uses the PDF's metadata,
// its existing field names, and the filename. Add new forms by adding entries.
//
// Each form can declare:
//   layoutConfig  — applied when the PDF is FLAT (no fillable fields yet)
//   addOnConfig   — applied when the PDF is ALREADY fillable (adds only your
//                   extra boxes; existing fields are kept untouched)
// Either may be null.

import { PDFDocument } from "pdf-lib";

export const FORMS = [
  {
    id: "w9",
    label: "IRS W-9 (Request for Taxpayer Identification Number)",
    patterns: [/\bw[\s\-_]?9\b/i, /request for taxpayer/i, /taxpayer identification number/i],
    layoutConfig: "configs/w9.json",
    addOnConfig: "configs/w9-add-signature.json",
  },
  {
    id: "w4",
    label: "IRS W-4 (Employee's Withholding Certificate)",
    patterns: [/\bw[\s\-_]?4\b/i, /employee'?s withholding/i],
    layoutConfig: null,
    addOnConfig: null,
  },
  {
    id: "i9",
    label: "USCIS I-9 (Employment Eligibility Verification)",
    patterns: [/\bi[\s\-_]?9\b/i, /employment eligibility verification/i],
    layoutConfig: null,
    addOnConfig: null,
  },
  {
    id: "eu-supplier",
    label: "EU Supplier / VAT registration",
    patterns: [/\bvat\b/i, /\biban\b/i, /supplier/i],
    layoutConfig: "configs/eu-supplier-a4.json",
    addOnConfig: null,
  },
];

// Load a PDF and report what's inside — without changing anything.
export async function inspectPdf(pdfBytes) {
  const pdf = await PDFDocument.load(pdfBytes);
  const form = pdf.getForm();
  const fields = form.getFields().map((f) => ({ name: f.getName(), type: f.constructor.name }));
  const meta = [pdf.getTitle(), pdf.getSubject(), pdf.getKeywords(), pdf.getAuthor()]
    .filter(Boolean)
    .join(" ");
  return {
    fields,
    fieldCount: fields.length,
    meta,
    pageSizes: pdf.getPages().map((p) => {
      const s = p.getSize();
      return { w: Math.round(s.width), h: Math.round(s.height) };
    }),
  };
}

// Score each known form against the metadata/field-names/filename; best wins.
export function detectForm(info, filename = "") {
  const hay = [info.meta, info.fields.map((f) => f.name).join(" "), filename]
    .join(" ")
    .toLowerCase();
  let def = null;
  let score = 0;
  for (const candidate of FORMS) {
    const s = candidate.patterns.reduce((n, re) => n + (re.test(hay) ? 1 : 0), 0);
    if (s > score) {
      def = candidate;
      score = s;
    }
  }
  return { def, score };
}
