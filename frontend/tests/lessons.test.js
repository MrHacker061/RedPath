import test from "node:test";
import assert from "node:assert/strict";

import { LESSONS, formatElapsed } from "../lessons.js";

const lessonButtons = ["network-scanning", "linux-commands"];

test("every lesson button has matching lesson content", () => {
  assert.deepEqual(Object.keys(LESSONS).sort(), [...lessonButtons].sort());
});

for (const [id, lesson] of Object.entries(LESSONS)) {
  const lastStep = lesson.steps.length - 1;

  test(`${id} ends with a knowledge check whose answer is a choice`, () => {
    const quiz = lesson.steps[lastStep];
    assert.ok(quiz.question);
    assert.ok(quiz.choices.includes(quiz.answer));
    assert.ok(lesson.steps.slice(0, lastStep).every((step) => step.paragraphs.length > 0));
  });

  test(`${id} reveals terminals and findings only at existing steps`, () => {
    const revealed = [...lesson.terminals.flat(), ...lesson.findings];
    assert.ok(revealed.every((item) => Number.isInteger(item.step) && item.step >= 0 && item.step <= lastStep));
    assert.ok(lesson.questions.every((entry) => entry.step <= lastStep));
  });

  test(`${id} gives every step a tab label, guide message, and hint`, () => {
    for (const step of lesson.steps) {
      assert.ok(step.label);
      assert.ok(step.guide);
      assert.ok(step.hints.length > 0);
    }
  });

  test(`${id} follow-up buttons point at real, uniquely named questions`, () => {
    const ids = lesson.questions.map((entry) => entry.id);
    assert.equal(new Set(ids).size, ids.length);
    for (const finding of lesson.findings.filter((item) => item.followUp)) {
      assert.ok(ids.includes(finding.followUp));
    }
  });
}

test("lesson timer formats hours, minutes, and seconds", () => {
  assert.equal(formatElapsed(0), "0:00:00");
  assert.equal(formatElapsed(65_400), "0:01:05");
  assert.equal(formatElapsed(5_057_000), "1:24:17");
});
