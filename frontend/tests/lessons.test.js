import test from "node:test";
import assert from "node:assert/strict";

import { LESSONS, formatElapsed } from "../lessons.js";
import { matchesTrainingCommand } from "../training-vm-lesson.js";

const lessonButtons = ["network-scanning", "linux-commands", "training-vm"];

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

test("training VM practice accepts only the scoped lesson commands", () => {
  const commands = LESSONS["training-vm"].steps.filter((step) => step.command).map((step) => step.command);
  assert.equal(commands.length, 3);
  for (const command of commands) {
    assert.equal(matchesTrainingCommand(`  ${command.replaceAll(" ", "  ")}  `, command), true);
  }
  assert.equal(matchesTrainingCommand("nmap -sV -Pn -p 1-65535 192.168.56.20", commands[0]), false);
  assert.equal(matchesTrainingCommand("nmap -sV -Pn -p 21,22 192.168.56.21", commands[0]), false);
});
