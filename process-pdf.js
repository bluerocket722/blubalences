#!/usr/bin/env node
//
// process-pdf.js — One-shot: read a PDF, detect which government form it is,
// KEEP any existing fillable fields exactly as they are, and only add the boxes
// you need (signature, etc.) when appropriate. Never flattens. Pure local
// processing — no network, no telemetry — so it is safe for EU data sovereignty.
//
//   • Already-fillable PDF  → existing fields kept untouched; add-on boxes added
//                             if the form has an add-on config, else left
//                             byte-for-byte identical.
//   • Flat PDF (no fields)  → the form's full layout is applied to make it
//                             fillable (if a layout config exists).
//
// Usage:  node process-pdf.js <input.pdf> [output.pdf]

import fs from "node:fs";
import path from "node:path";
import { inspectPdf, detectForm } from "./lib/form-registry.js";
import { stampForm } from "./lib/stamp-form.js";

async function main() {
  const [, , inputPath, outputPath] = process.argv;
  if (!inputPath) {
    console.error("Usage: node process-pdf.js <input.pdf> [output.pdf]");
    process.exit(1);
  }

  const filename = path.basename(inputPath);
  const pdfBytes = fs.readFileSync(path.resolve(inputPath));
  const info = await inspectPdf(pdfBytes);
  const { def, score } = detectForm(info, filename);
  const out = outputPath || inputPath.replace(/\.pdf$/i, "-processed.pdf");

  console.log(`\n  Input: ${filename}`);
  console.log(`  Pages: ${info.pageSizes.map((s) => `${s.w}x${s.h}`).join(", ")}`);
  console.log(`  Already-fillable fields: ${info.fieldCount}`);
  console.log(`  Detected form: ${def ? def.label : "Unknown"}${def ? ` (match score ${score})` : ""}`);

  const alreadyFillable = info.fieldCount > 0;
  const configPath = def ? (alreadyFillable ? def.addOnConfig : def.layoutConfig) : null;

  if (!configPath) {
    // Nothing to add — keep the document byte-for-byte identical (best way to
    // guarantee an existing fillable form "remains the same").
    fs.writeFileSync(path.resolve(out), pdfBytes);
    console.log(
      alreadyFillable
        ? `  Action: already fillable — left unchanged (no add-on configured for this form).`
        : `  Action: no layout available for this form — left unchanged.`,
    );
    console.log(`  Written to: ${out}\n`);
    return;
  }

  const config = JSON.parse(fs.readFileSync(path.resolve(configPath), "utf-8"));
  const { bytes, report } = await stampForm(pdfBytes, config);
  fs.writeFileSync(path.resolve(out), bytes);

  console.log(`  Applied config: ${configPath}`);
  if (report.preexistingFieldCount > 0) {
    console.log(`  Kept ${report.preexistingFieldCount} existing field(s) untouched (still fillable).`);
  }
  console.log(
    `  Added ${report.created.length} new field(s)` +
      (report.skipped.length ? `, skipped ${report.skipped.length} already present` : "") +
      ".",
  );
  if (report.errors.length) report.errors.forEach((e) => console.log(`  ! ${e}`));
  console.log(`  Written to: ${out}\n`);
}

main().catch((e) => {
  console.error("Error:", e.message);
  process.exit(1);
});
