#!/usr/bin/env node
//
// generate-blank-w9.js - Creates a synthetic blank W-9 PDF (for testing).
// Output: blank-w9.pdf

const fs = require("fs");
const { PDFDocument, rgb, StandardFonts } = require("pdf-lib");

async function main() {
  const pdf = await PDFDocument.create();
  const page = pdf.addPage([612, 792]);
  const font = await pdf.embedFont(StandardFonts.Helvetica);
  const bold = await pdf.embedFont(StandardFonts.HelveticaBold);
  const gray = rgb(0.4, 0.4, 0.4);
  const black = rgb(0, 0, 0);
  const lineColor = rgb(0.7, 0.7, 0.7);

  page.drawText("Form W-9", { x: 36, y: 750, size: 18, font: bold, color: black });
  page.drawText("(Rev. October 2018)", { x: 36, y: 735, size: 8, font, color: gray });
  page.drawText("Request for Taxpayer Identification Number and Certification", { x: 160, y: 750, size: 11, font: bold, color: black });
  page.drawText("Department of the Treasury - Internal Revenue Service", { x: 160, y: 736, size: 8, font, color: gray });
  page.drawLine({ start: { x: 36, y: 725 }, end: { x: 576, y: 725 }, thickness: 1, color: black });
  page.drawText("Give Form to the requester. Do not send to the IRS.", { x: 360, y: 715, size: 8, font, color: gray });

  page.drawText("1  Name (as shown on your income tax return). Name is required on this line; do not leave this line blank.", { x: 36, y: 670, size: 8, font, color: black });
  page.drawLine({ start: { x: 36, y: 645 }, end: { x: 576, y: 645 }, thickness: 0.5, color: lineColor });

  page.drawText("2  Business name/disregarded entity name, if different from above", { x: 36, y: 636, size: 8, font, color: black });
  page.drawLine({ start: { x: 36, y: 613 }, end: { x: 576, y: 613 }, thickness: 0.5, color: lineColor });

  page.drawText("3  Check appropriate box for federal tax classification of the person whose name is entered on line 1.", { x: 36, y: 600, size: 7.5, font, color: black });

  const checkLabels = [
    { label: "Individual/sole proprietor or single-member LLC", x: 56 },
    { label: "C Corporation", x: 280 },
    { label: "S Corporation", x: 332 },
    { label: "Partnership", x: 384 },
    { label: "Trust/estate", x: 418 },
  ];
  for (const cl of checkLabels) {
    page.drawRectangle({ x: cl.x - 14, y: 580, width: 10, height: 10, borderWidth: 0.5, borderColor: black, color: rgb(1, 1, 1) });
    page.drawText(cl.label, { x: cl.x, y: 583, size: 6.5, font, color: black });
  }

  page.drawRectangle({ x: 42, y: 568, width: 10, height: 10, borderWidth: 0.5, borderColor: black, color: rgb(1, 1, 1) });
  page.drawText("Limited liability company. Enter the tax classification (C=C corporation, S=S corporation, P=Partnership) >", { x: 56, y: 571, size: 6.5, font, color: black });
  page.drawLine({ start: { x: 395, y: 568 }, end: { x: 415, y: 568 }, thickness: 0.5, color: lineColor });

  page.drawRectangle({ x: 246, y: 568, width: 10, height: 10, borderWidth: 0.5, borderColor: black, color: rgb(1, 1, 1) });
  page.drawText("Other (see instructions) >", { x: 260, y: 571, size: 6.5, font, color: black });

  page.drawText("4  Exemptions (codes apply only to", { x: 422, y: 600, size: 7, font, color: black });
  page.drawText("certain entities, not individuals):", { x: 422, y: 591, size: 7, font, color: black });
  page.drawText("Exempt payee code (if any)", { x: 422, y: 576, size: 6.5, font, color: gray });
  page.drawLine({ start: { x: 422, y: 570 }, end: { x: 492, y: 570 }, thickness: 0.5, color: lineColor });
  page.drawText("Exemption from FATCA reporting code (if any)", { x: 502, y: 576, size: 5, font, color: gray });
  page.drawLine({ start: { x: 502, y: 570 }, end: { x: 576, y: 570 }, thickness: 0.5, color: lineColor });

  page.drawText("5  Address (number, street, and apt. or suite no.) See instructions.", { x: 36, y: 560, size: 8, font, color: black });
  page.drawLine({ start: { x: 36, y: 555 }, end: { x: 416, y: 555 }, thickness: 0.5, color: lineColor });

  page.drawText("6  City, state, and ZIP code", { x: 36, y: 541, size: 8, font, color: black });
  page.drawLine({ start: { x: 36, y: 526 }, end: { x: 416, y: 526 }, thickness: 0.5, color: lineColor });

  page.drawText("Requester's name and address (optional)", { x: 422, y: 545, size: 6.5, font, color: gray });
  page.drawRectangle({ x: 422, y: 520, width: 154, height: 35, borderWidth: 0.5, borderColor: lineColor, color: rgb(1, 1, 1) });

  page.drawText("7  List account number(s) here (optional)", { x: 36, y: 510, size: 8, font, color: black });
  page.drawLine({ start: { x: 36, y: 496 }, end: { x: 416, y: 496 }, thickness: 0.5, color: lineColor });

  page.drawLine({ start: { x: 36, y: 485 }, end: { x: 576, y: 485 }, thickness: 1.5, color: black });
  page.drawText("Part I", { x: 36, y: 474, size: 10, font: bold, color: black });
  page.drawText("Taxpayer Identification Number (TIN)", { x: 80, y: 474, size: 10, font, color: black });

  page.drawText("Social security number", { x: 422, y: 478, size: 7, font, color: black });
  for (let i = 0; i < 9; i++) {
    let x = 422 + i * 17.5;
    if (i >= 3) x += 6;
    if (i >= 5) x += 6;
    page.drawRectangle({ x, y: 462, width: 16, height: 18, borderWidth: 0.5, borderColor: black, color: rgb(1, 1, 1) });
  }

  page.drawText("Employer identification number", { x: 422, y: 452, size: 7, font, color: black });
  for (let i = 0; i < 9; i++) {
    let x = 422 + i * 17.5;
    if (i >= 2) x += 6;
    page.drawRectangle({ x, y: 436, width: 16, height: 18, borderWidth: 0.5, borderColor: black, color: rgb(1, 1, 1) });
  }

  page.drawLine({ start: { x: 36, y: 420 }, end: { x: 576, y: 420 }, thickness: 1.5, color: black });
  page.drawText("Part II", { x: 36, y: 408, size: 10, font: bold, color: black });
  page.drawText("Certification", { x: 80, y: 408, size: 10, font, color: black });
  page.drawText("Under penalties of perjury, I certify that:", { x: 36, y: 395, size: 8, font, color: black });
  page.drawText("1. The number shown on this form is my correct taxpayer identification number, and", { x: 36, y: 380, size: 7.5, font, color: gray });
  page.drawText("2. I am not subject to backup withholding because: (a) I am exempt from backup withholding, or (b) I have not been notified by the IRS...", { x: 36, y: 368, size: 7, font, color: gray });

  page.drawLine({ start: { x: 36, y: 115 }, end: { x: 576, y: 115 }, thickness: 1, color: black });
  page.drawText("Sign Here", { x: 36, y: 104, size: 9, font: bold, color: black });
  page.drawText("Signature of", { x: 36, y: 86, size: 7, font, color: gray });
  page.drawText("U.S. person >", { x: 36, y: 78, size: 7, font, color: gray });
  page.drawLine({ start: { x: 100, y: 90 }, end: { x: 430, y: 90 }, thickness: 0.5, color: black });
  page.drawText("Date >", { x: 440, y: 86, size: 7, font, color: gray });
  page.drawLine({ start: { x: 470, y: 90 }, end: { x: 576, y: 90 }, thickness: 0.5, color: black });

  const bytes = await pdf.save();
  fs.writeFileSync("blank-w9.pdf", bytes);
  console.log("Created: blank-w9.pdf");
}

main();
