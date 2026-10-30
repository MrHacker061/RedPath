
export function initializeLessons() {
  const startLessonButton = document.querySelector("#start-lesson");
  const lessonContent = document.querySelector("#lesson-content");

  if (!startLessonButton || !lessonContent) return;

  // Helper function for creating HTML elements
  function createElement(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  // Helper function for creating buttons
  function createButton(text, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", onClick);
    return button;
  }

  // Display the requested lesson step
  function showStep(step) {

    // STEP 1: Introduction
    if (step === 1) {
      const heading = createElement(
        "h3",
        "Step 1: Understanding Network Scanning"
      );

      const introduction = createElement(
        "p",
        "Network scanning is a technique used to identify " +
        "open ports and available services on a computer " +
        "or network. It helps cybersecurity professionals " +
        "understand what services a system exposes."
      );

      const explanation = createElement(
        "p",
        "A port is a numbered communication endpoint. " +
        "For example, port 22 is commonly used for SSH, " +
        "while port 80 is commonly used for HTTP."
      );

      const reminder = createElement(
        "p",
        "Important: Only scan systems you own or have " +
        "explicit permission to test."
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
        "Imagine you performed an authorized network scan. " +
        "Examine the following simulated results:"
      );

      const scanResults = createElement(
        "pre",
        "PORT     STATE    SERVICE\n" +
        "22/tcp   open     ssh\n" +
        "80/tcp   closed   http"
      );

      const explanation = createElement(
        "p",
        "Port 22 is open, indicating that the scan found " +
        "an accessible SSH service. Port 80 is closed, " +
        "meaning no service is accepting connections " +
        "on that port from the scanned perspective."
      );

      const reminder = createElement(
        "p",
        "Remember: An open port does not automatically " +
        "mean that a system is vulnerable."
      );

      const backButton = createButton(
        "Back",
        () => showStep(1)
      );
      backButton.className = "secondary-button";

      const nextButton = createButton(
        "Next Step",
        () => showStep(3)
      );

      const controls = createElement("div", "");
      controls.className = "proposal-controls";
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
        "Based on the previous scan results, " +
        "which TCP port was open?"
      );

      const quizForm = document.createElement("form");
      const choices = ["22/tcp", "80/tcp", "443/tcp"];

      const fieldset = document.createElement("fieldset");
      const legend = createElement(
        "legend",
        "Select one answer:"
      );
      fieldset.append(legend);

      choices.forEach((choice) => {
        const label = document.createElement("label");
        label.style.display = "block";

        const input = document.createElement("input");
        input.type = "radio";
        input.name = "lesson-answer";
        input.value = choice;

        label.append(
          input,
          document.createTextNode(" " + choice)
        );

        fieldset.append(label);
      });

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
        () => showStep(4)
      );
      completeButton.hidden = true;

      quizForm.addEventListener("submit", (event) => {
        event.preventDefault();

        const selected = quizForm.querySelector(
          'input[name="lesson-answer"]:checked'
        );

        if (!selected) {
          feedback.textContent = "Please select an answer.";
          feedback.dataset.state = "error";
          return;
        }

        if (selected.value === "22/tcp") {
          feedback.textContent =
            "Correct! Port 22 was open and running SSH.";
          feedback.dataset.state = "healthy";
          completeButton.hidden = false;
        } else {
          feedback.textContent =
            "Not quite! Review the scan results and try again.";
          feedback.dataset.state = "error";
          completeButton.hidden = true;
        }
      });

      const controls = createElement("div", "");
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
        "Congratulations! You completed the Introduction " +
        "to Network Scanning lesson."
      );

      const summary = createElement(
        "p",
        "You learned about network ports, common services, " +
        "and how to interpret basic network scan results."
      );

      const nextSteps = createElement(
        "p",
        "You are now ready to continue learning about " +
        "network security in an authorized lab environment."
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

  // Start the lesson when the student clicks the button
  startLessonButton.addEventListener("click", () => {
    startLessonButton.textContent = "Lesson Started";
    startLessonButton.disabled = true;

    showStep(1);
  });
}
