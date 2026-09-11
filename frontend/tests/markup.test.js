import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

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
