#!/usr/bin/env node
//
// make-fillable.js — Adds AcroForm fields to a flat PDF using a JSON config.
// Usage:  node make-fillable.js <input.pdf> <config.json> [output.pdf]
//
// PRIVACY: Never logs, prints, or persists field contents.

const fs = require("fs");
const path = require("path");
const { PDFDocument, PDFTextField, PDFCheckBox, rgb, StandardFonts } = require("pdf-lib");

async function main() {
  const [,, inputPath, configPath, outputPath] = process.argv;

  if (!inputPath || !configPath) {
    console.error("Usage: node make-fillable.js <input.pdf> <config.json> [output.pdf]");
    process.exit(1);
  }

  const config = JSON.parse(fs.readFileSync(path.resolve(configPath), "utf-8"));
  const pdfBytes = fs.readFileSync(path.resolve(inputPath));
  const pdf = await PDFDocument.load(pdfBytes);
  const form = pdf.getForm();
  const font = await pdf.embedFont(StandardFonts.Helvetica);

  for (const [pageNum, pageCfg] of Object.entries(config.pages)) {
    const pageIdx = Number(pageNum) - 1;
    const page = pdf.getPage(pageIdx);
    const { height: pageH } = page.getSize();

    if (pageCfg.textFields) {
      for (const f of pageCfg.textFields) {
        addTextField(form, page, f, pageH, font);
      }
    }

    if (pageCfg.checkboxes) {
      for (const cb of pageCfg.checkboxes) {
        addCheckbox(form, page, cb, pageH);
      }
    }

    if (pageCfg.llcClassification) {
      addTextField(form, page, pageCfg.llcClassification, pageH, font);
    }

    if (pageCfg.ssnField) {
      addSegmentedField(form, page, pageCfg.ssnField, 9, "ssn", pageH, font);
    }

    if (pageCfg.einField) {
      addSegmentedField(form, page, pageCfg.einField, 9, "ein", pageH, font);
    }

    if (pageCfg.signatureFields) {
      for (const sf of pageCfg.signatureFields) {
        addTextField(form, page, sf, pageH, font);
      }
    }
  }

  const filled = await pdf.save();
  const out = outputPath || inputPath.replace(/\.pdf$/i, "-fillable.pdf");
  fs.writeFileSync(path.resolve(out), filled);
  console.log(`Fillable PDF written to: ${out}`);
  console.log(`Fields created: ${form.getFields().length}`);
}

function addTextField(form, page, cfg, pageH, font) {
  const field = form.createTextField(cfg.name);
  field.addToPage(page, {
    x: cfg.x,
    y: cfg.y,
    width: cfg.width,
    height: cfg.height,
    font,
    borderWidth: 0.5,
    borderColor: rgb(0.6, 0.6, 0.6),
    backgroundColor: rgb(0.95, 0.97, 1.0),
  });
  if (cfg.maxLength) field.setMaxLength(cfg.maxLength);
  field.enableReadOnly();
  field.disableReadOnly();
}

function addCheckbox(form, page, cfg, pageH) {
  const cb = form.createCheckBox(cfg.name);
  cb.addToPage(page, {
    x: cfg.x,
    y: cfg.y,
    width: cfg.size,
    height: cfg.size,
    borderWidth: 0.5,
    borderColor: rgb(0.5, 0.5, 0.5),
    backgroundColor: rgb(0.95, 0.97, 1.0),
  });
}

function addSegmentedField(form, page, cfg, totalDigits, prefix, pageH, font) {
  let curX = cfg.startX;
  let digitIdx = 0;

  for (let i = 0; i < totalDigits; i++) {
    const fieldName = `${prefix}_digit_${i + 1}`;
    const field = form.createTextField(fieldName);
    field.addToPage(page, {
      x: curX,
      y: cfg.y,
      width: cfg.digitWidth,
      height: cfg.digitHeight,
      font,
      borderWidth: 0.5,
      borderColor: rgb(0.6, 0.6, 0.6),
      backgroundColor: rgb(0.95, 0.97, 1.0),
    });
    field.setMaxLength(1);
    field.setFontSize(cfg.fontSize || 12);

    curX += cfg.digitWidth + cfg.gap;
    digitIdx++;

    if (cfg.dashAfter && cfg.dashAfter.includes(digitIdx)) {
      curX += cfg.dashWidth;
    }
  }
}

main().catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
