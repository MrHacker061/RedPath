import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const lessonsHtml = await readFile(new URL("../lessons.html", import.meta.url), "utf8");

test("dashboard provides navigation and semantic page landmarks", () => {
  assert.match(html, /<header[ >]/);
  assert.match(html, /<nav aria-label="Primary navigation">/);
  assert.match(html, /<main id="main-content">/);
  assert.match(html, /<footer[ >]/);
});

test("loading and error updates are announced to assistive technology", () => {
  assert.match(html, /id="health-message"[^>]*role="status"[^>]*aria-live="polite"/);
});

test("each service has one labeled health card", () => {
  for (const service of ["fastapi", "ollama", "kali"]) {
    assert.equal((html.match(new RegExp(`data-service="${service}"`, "g")) || []).length, 1);
  }
});

test("page includes a keyboard skip link", () => {
  assert.match(html, /<a class="skip-link" href="#main-content">/);
});

test("session form separates lesson URL from authorized target", () => {
  assert.match(html, /name="lesson_url"/);
  assert.match(html, /name="target"/);
  assert.match(html, /name="authorization_confirmed"/);
});

test("evidence workspace accepts XML and labels evidence states", () => {
  assert.match(html, /accept="\.xml,application\/xml,text\/xml"/);
  assert.match(html, /Observed scan facts, AI inferences, and verified results/);
  assert.match(html, /id="findings-body"/);
});

test("recommendation and policy decision use separate labeled regions", () => {
  assert.match(html, /id="ai-recommendation"[^>]*aria-labelledby="ai-recommendation-title"/);
  assert.match(html, /id="policy-decision"[^>]*aria-labelledby="policy-decision-title"/);
  assert.match(html, /id="recommendation-finding-ids"/);
  assert.match(html, /id="recommendation-arguments"/);
});

test("exact proposal controls are native buttons with an announced state", () => {
  assert.match(html, /id="approve-proposal"[^>]*type="button"/);
  assert.match(html, /id="reject-proposal"[^>]*type="button"/);
  assert.match(html, /id="proposal-state"[^>]*role="status"[^>]*aria-live="polite"/);
});

test("emergency stop has separate accessible activate and clear controls", () => {
  assert.match(html, /id="emergency-stop"[^>]*type="button"/);
  assert.match(html, /id="clear-emergency-stop"[^>]*type="button"/);
  assert.match(html, /id="emergency-stop-state"[^>]*role="status"[^>]*aria-live="polite"/);
  assert.match(html, /does not confirm that running work was cancelled/i);
});

test("session oversight provides accessible report and audit regions", () => {
  assert.match(html, /id="refresh-oversight"[^>]*type="button"/);
  assert.match(html, /id="report-summary"[^>]*aria-labelledby="report-summary-title"/);
  assert.match(html, /id="report-proposals"[^>]*aria-label="Policy proposals"/);
  assert.match(html, /id="report-approvals"[^>]*aria-label="Approval decisions"/);
  assert.match(html, /id="audit-history"[^>]*aria-labelledby="audit-history-title"/);
});

test("guided workflow exposes only the guarded exact-proposal execution control", () => {
  assert.match(html, /id="run-proposal"[^>]*type="button"[^>]*disabled/);
  assert.match(html, /id="run-controls"[^>]*hidden/);
  assert.match(html, /id="proposal-state"[^>]*tabindex="-1"/);
  assert.doesNotMatch(html, /(?:command|action_name|distribution)[^>]*name=/i);
  assert.match(html, /id="execution-notice"[^>]*role="status"[^>]*aria-live="polite"/);
});

test("setup, lab, approval, results, report, and settings are semantic regions", () => {
  for (const section of ["setup", "dashboard", "lab", "approval", "results", "report", "settings"]) {
    assert.match(html, new RegExp(`<section id="${section}"[^>]*aria-labelledby=`));
  }
  assert.match(html, /id="setup-repair"[^>]*type="button"/);
  assert.match(html, /id="setup-cancel"[^>]*type="button"/);
  assert.match(html, /id="diagnostics"[^>]*aria-live="polite"/);
});

test("lessons open on their own page instead of the dashboard", () => {
  assert.match(html, /<a href="\/lessons">Lessons<\/a>/);
  assert.doesNotMatch(html, /id="lessons"/);
  assert.match(lessonsHtml, /<nav aria-label="Primary navigation">/);
  assert.match(lessonsHtml, /<a href="\/lessons" aria-current="page">/);
  assert.match(lessonsHtml, /<a class="lab-brand" href="\/">/);
});

test("lessons page provides landmarks and the lesson workspace", () => {
  assert.match(lessonsHtml, /<a class="skip-link" href="#main-content">/);
  assert.match(lessonsHtml, /<main id="main-content"/);
  assert.match(lessonsHtml, /id="lesson-library"[^>]*aria-labelledby="lesson-library-title"/);
  assert.match(lessonsHtml, /id="active-lesson"[^>]*aria-labelledby="active-lesson-title"[^>]*hidden/);
  for (const id of ["lesson-terminals", "lesson-steps", "lesson-content", "lesson-takeaways", "exit-lesson", "lesson-timer"]) {
    assert.match(lessonsHtml, new RegExp(`id="${id}"`));
  }
  assert.match(lessonsHtml, /data-lesson-id="network-scanning"/);
  assert.match(lessonsHtml, /data-lesson-id="linux-commands"/);
  assert.match(lessonsHtml, /<script type="module" src="\/assets\/lessons-page\.js">/);
});

test("lessons page labels its environment as simulated", () => {
  assert.equal((lessonsHtml.match(/class="status-pill">Simulated</g) || []).length, 3);
  assert.match(lessonsHtml, /aria-label="Simulated lesson environment"/);
});

test("why this matters panel is a disclosure and the guide uses labeled tabs", () => {
  assert.match(lessonsHtml, /id="why-toggle"[^>]*type="button"[^>]*aria-expanded="true"[^>]*aria-controls="why-panel-body"/);
  for (const panel of ["chat", "findings", "hints"]) {
    assert.match(lessonsHtml, new RegExp(`id="guide-tab-${panel}"[^>]*role="tab"[^>]*aria-controls="guide-${panel}"`));
    assert.match(lessonsHtml, new RegExp(`id="guide-${panel}"[^>]*role="tabpanel"[^>]*aria-labelledby="guide-tab-${panel}"`));
  }
  assert.match(lessonsHtml, /id="guide-messages"[^>]*aria-live="polite"/);
});
