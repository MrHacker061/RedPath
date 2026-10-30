
export function initializeLessons() {
  const startLessonButton = document.querySelector("#start-lesson");
  const lessonContent = document.querySelector("#lesson-content");
  const lessonProgress = document.querySelector("#lesson-progress");
  const lessonProgressBar = document.querySelector("#lesson-progress-bar");

  if (!startLessonButton || !lessonContent || !lessonProgress || !lessonProgressBar) {
    return;
  }

  function createElement(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  function createButton(text, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", onClick);
    return button;
  }

  function updateProgress(step) {
    // Three learning steps, followed by a completion screen.
    const completed = step === 4;

    lessonProgress.textContent = completed
      ? "Lesson complete — 3 of 3 steps finished"
      : `Step ${step} of 3`;

    lessonProgressBar.value = Math.min(step, 3);
    lessonProgress.hidden = false;
    lessonProgressBar.hidden = false;
  }

  function showStep(step) {
    updateProgress(step);

    // STEP 1: Introduction
    if (step === 1) {
      const heading = createElement(
        "h3",
        "Step 1: Understanding Network Scanning"
      );

      const introduction = createElement(
        "p",
        "Network scanning identifies open ports and services on an authorized " +
        "computer or network. It helps you understand what a system exposes."
      );

      const explanation = createElement(
        "p",
        "A port is a numbered communication endpoint. Port 22 is commonly " +
        "used for SSH, and port 80 is commonly used for HTTP."
      );

      const reminder = createElement(
        "p",
        "Only scan systems you own or have explicit permission to test."
      );

      const nextButton = createButton(
        "Next Step",
        () => showStep(2)
      );

      lessonContent.replaceChildren(
        heading,
        introduction,
        explanation,
        reminder,
        nextButton
      );
    }

    // STEP 2: Guided practice
    else if (step === 2) {
      const heading = createElement(
        "h3",
        "Step 2: Understanding Scan Results"
      );

      const instructions = createElement(
        "p",
        "Examine these simulated results from an authorized network scan. " +
        "No real scan is performed in this lesson."
      );

      const scanResults = createElement(
        "pre",
        "PORT     STATE    SERVICE\n" +
        "22/tcp   open     ssh\n" +
        "80/tcp   closed   http"
      );

      const explanation = createElement(
        "p",
        "Port 22 is open, indicating an accessible SSH service from the " +
        "scanner's perspective. Port 80 is closed, indicating that no " +
        "service accepted the scan's connection attempts on that port."
      );

      const reminder = createElement(
        "p",
        "An open port does not automatically mean a system is vulnerable."
      );

      const controls = document.createElement("div");
      controls.className = "proposal-controls";

      const backButton = createButton(
        "Back",
        () => showStep(1)
      );
      backButton.className = "secondary-button";

      const nextButton = createButton(
        "Next Step",
        () => showStep(3)
      );

      controls.append(backButton, nextButton);

      lessonContent.replaceChildren(
        heading,
        instructions,
        scanResults,
        explanation,
        reminder,
        controls
      );
    }

    // STEP 3: Knowledge check
    else if (step === 3) {
      const heading = createElement(
        "h3",
        "Step 3: Knowledge Check"
      );

      const instructions = createElement(
        "p",
        "Based on the previous scan results, which TCP port was open?"
      );

      const quizForm = document.createElement("form");
      const fieldset = document.createElement("fieldset");

      fieldset.append(
        createElement("legend", "Select one answer:")
      );

      const choices = ["22/tcp", "80/tcp", "443/tcp"];

      for (const choice of choices) {
        const label = document.createElement("label");
        label.style.display = "block";

        const input = document.createElement("input");
        input.type = "radio";
        input.name = "lesson-answer";
        input.value = choice;

        label.append(
          input,
          document.createTextNode(` ${choice}`)
        );

        fieldset.append(label);
      }

      const feedback = createElement("p", "");
      feedback.setAttribute("role", "status");

      const checkButton = document.createElement("button");
      checkButton.type = "submit";
      checkButton.textContent = "Check Answer";

      const backButton = createButton(
        "Back",
        () => showStep(2)
      );
      backButton.className = "secondary-button";

      const completeButton = createButton(
        "Complete Lesson",
        () => {
          const selected = quizForm.querySelector(
            'input[name="lesson-answer"]:checked'
          );

          if (selected?.value === "22/tcp") {
            showStep(4);
          }
        }
      );

      completeButton.hidden = true;

      // Reset feedback when the student changes an answer.
      fieldset.addEventListener("change", () => {
        feedback.textContent = "";
        feedback.dataset.state = "";
        completeButton.hidden = true;
      });

      quizForm.addEventListener("submit", (event) => {
        event.preventDefault();

        const selected = quizForm.querySelector(
          'input[name="lesson-answer"]:checked'
        );

        if (!selected) {
          feedback.textContent = "Please select an answer.";
          feedback.dataset.state = "error";
          completeButton.hidden = true;
        } else if (selected.value === "22/tcp") {
          feedback.textContent =
            "Correct! Port 22 was open and associated with SSH.";
          feedback.dataset.state = "healthy";
          completeButton.hidden = false;
        } else {
          feedback.textContent =
            "Not quite! Review the scan results and try again.";
          feedback.dataset.state = "error";
          completeButton.hidden = true;
        }
      });

      const controls = document.createElement("div");
      controls.className = "proposal-controls";

      controls.append(backButton, checkButton);

      quizForm.append(
        fieldset,
        controls,
        feedback,
        completeButton
      );

      lessonContent.replaceChildren(
        heading,
        instructions,
        quizForm
      );
    }

    // STEP 4: Lesson completion
    else if (step === 4) {
      const heading = createElement(
        "h3",
        "Lesson Complete!"
      );

      const congratulations = createElement(
        "p",
        "Congratulations! You completed Introduction to Network Scanning."
      );

      const summary = createElement(
        "p",
        "You learned about ports, services, and interpreting basic " +
        "network scan results."
      );

      const nextSteps = createElement(
        "p",
        "Continue practicing only in an authorized lab environment."
      );

      const restartButton = createButton(
        "Restart Lesson",
        () => showStep(1)
      );

      lessonContent.replaceChildren(
        heading,
        congratulations,
        summary,
        nextSteps,
        restartButton
      );
    }

    lessonContent.hidden = false;
  }

  // Start the lesson
  startLessonButton.addEventListener("click", () => {
    startLessonButton.textContent = "Lesson Started";
    startLessonButton.disabled = true;

    showStep(1);
  });
}
