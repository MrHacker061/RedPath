
/*
 * RedPath beginner lessons.
 * All terminal examples are simulated.
 * No real commands or scans are executed.
 */

const LESSONS = {
  "network-scanning": {
    title: "Introduction to Network Scanning",
    steps: [
      {
        title: "Understanding Network Scanning",
        paragraphs: [
          "Network scanning identifies open ports and services on an authorized computer or network. It helps you understand what a system exposes.",
          "A port is a numbered communication endpoint. Port 22 is commonly used for SSH, and port 80 is commonly used for HTTP.",
          "Only scan systems you own or have explicit permission to test."
        ]
      },
      {
        title: "Understanding Scan Results",
        paragraphs: [
          "Examine these simulated results from an authorized network scan. No real scan is performed in this lesson."
        ],
        example:
          "PORT     STATE    SERVICE\n" +
          "22/tcp   open     ssh\n" +
          "80/tcp   closed   http",
        afterExample: [
          "Port 22 is open and associated with SSH. Port 80 is closed in this example.",
          "An open port does not automatically mean that a system is vulnerable."
        ]
      },
      {
        title: "Knowledge Check",
        question:
          "Based on the previous scan results, which TCP port was open?",
        choices: ["22/tcp", "80/tcp", "443/tcp"],
        answer: "22/tcp",
        correctFeedback:
          "Correct! Port 22 was open and associated with SSH.",
        wrongFeedback:
          "Not quite! Review the simulated scan results and try again."
      }
    ],
    completion:
      "You learned about ports, services, and interpreting basic network scan results."
  },

  "linux-commands": {
    title: "Introduction to Linux Commands",
    steps: [
      {
        title: "Understanding the Linux Terminal",
        paragraphs: [
          "The Linux terminal lets you interact with the operating system by entering text commands.",
          "The pwd command shows your current directory, ls lists files and folders, and whoami shows the current username.",
          "In RedPath, practice commands only in a controlled, authorized learning environment."
        ]
      },
      {
        title: "Reading Terminal Output",
        paragraphs: [
          "These are simulated Linux terminal examples. No commands are actually executed."
        ],
        example:
          "kali@redpath:~$ pwd\n" +
          "/home/kali\n\n" +
          "kali@redpath:~$ ls\n" +
          "notes.txt  labs\n\n" +
          "kali@redpath:~$ whoami\n" +
          "kali",
        afterExample: [
          "pwd prints /home/kali, which is the current directory in this example.",
          "ls lists the contents of that directory, while whoami reports the current username."
        ]
      },
      {
        title: "Knowledge Check",
        question:
          "Which Linux command displays your current directory?",
        choices: ["ls", "pwd", "whoami"],
        answer: "pwd",
        correctFeedback:
          "Correct! pwd prints the current working directory.",
        wrongFeedback:
          "Not quite! Think about which command prints the working directory."
      }
    ],
    completion:
      "You learned how pwd, ls, and whoami help you understand a Linux terminal session."
  }
};

export function initializeLessons() {
  const library = document.querySelector("#lesson-library");
  const activeLessonPanel = document.querySelector("#active-lesson");
  const activeLessonTitle = document.querySelector("#active-lesson-title");
  const backToLessonsButton = document.querySelector("#back-to-lessons");
  const lessonContent = document.querySelector("#lesson-content");
  const lessonProgress = document.querySelector("#lesson-progress");
  const lessonProgressBar = document.querySelector("#lesson-progress-bar");

  if (
    !library ||
    !activeLessonPanel ||
    !activeLessonTitle ||
    !backToLessonsButton ||
    !lessonContent ||
    !lessonProgress ||
    !lessonProgressBar
  ) {
    return;
  }

  let currentLesson = null;

  function createElement(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  function createButton(text, onClick, secondary = false) {
    const button = createElement("button", text);
    button.type = "button";

    if (secondary) {
      button.className = "secondary-button";
    }

    button.addEventListener("click", onClick);
    return button;
  }

  function showLibrary() {
    currentLesson = null;
    activeLessonPanel.hidden = true;
    library.hidden = false;
    lessonContent.replaceChildren();
    lessonContent.hidden = true;
  }

  function showStep(index) {
    if (!currentLesson) {
      return;
    }

    const total = currentLesson.steps.length;
    const finished = index === total;

    lessonProgress.textContent = finished
      ? `Lesson complete — ${total} of ${total} steps finished`
      : `Step ${index + 1} of ${total}`;

    lessonProgressBar.max = total;
    lessonProgressBar.value = finished ? total : index + 1;

    lessonProgress.hidden = false;
    lessonProgressBar.hidden = false;

    // Lesson completion screen
    if (finished) {
      const heading = createElement("h3", "Lesson Complete!");

      const message = createElement(
        "p",
        `Congratulations! You completed ${currentLesson.title}.`
      );

      const summary = createElement(
        "p",
        currentLesson.completion
      );

      const reminder = createElement(
        "p",
        "Continue practicing only in an authorized lab environment."
      );

      const controls = document.createElement("div");
      controls.className = "proposal-controls";

      controls.append(
        createButton("Restart Lesson", () => showStep(0)),
        createButton("Choose Another Lesson", showLibrary, true)
      );

      lessonContent.replaceChildren(
        heading,
        message,
        summary,
        reminder,
        controls
      );

      lessonContent.hidden = false;
      return;
    }

    const step = currentLesson.steps[index];

    const heading = createElement(
      "h3",
      `Step ${index + 1}: ${step.title}`
    );

    const content = [heading];

    // Quiz step
    if (step.question) {
      const question = createElement("p", step.question);

      const form = document.createElement("form");
      const fieldset = document.createElement("fieldset");

      fieldset.append(
        createElement("legend", "Select one answer:")
      );

      for (const choice of step.choices) {
        const label = document.createElement("label");
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

      const buttons = document.createElement("div");
      buttons.className = "proposal-controls";

      buttons.append(
        createButton("Back", () => showStep(index - 1), true)
      );

      const checkButton = createElement(
        "button",
        "Check Answer"
      );

      checkButton.type = "submit";
      buttons.append(checkButton);

      const completeButton = createButton(
        "Complete Lesson",
        () => {
          const selected = form.querySelector(
            'input[name="lesson-answer"]:checked'
          );

          if (selected?.value === step.answer) {
            showStep(total);
          }
        }
      );

      completeButton.hidden = true;

      // Reset feedback if the student changes answers.
      fieldset.addEventListener("change", () => {
        feedback.textContent = "";
        feedback.dataset.state = "";
        completeButton.hidden = true;
      });

      form.addEventListener("submit", (event) => {
        event.preventDefault();

        const selected = form.querySelector(
          'input[name="lesson-answer"]:checked'
        );

        if (!selected) {
          feedback.textContent = "Please select an answer.";
          feedback.dataset.state = "error";
          completeButton.hidden = true;
        } else if (selected.value === step.answer) {
          feedback.textContent = step.correctFeedback;
          feedback.dataset.state = "healthy";
          completeButton.hidden = false;
        } else {
          feedback.textContent = step.wrongFeedback;
          feedback.dataset.state = "error";
          completeButton.hidden = true;
        }
      });

      form.append(
        fieldset,
        buttons,
        feedback,
        completeButton
      );

      content.push(question, form);
    }

    // Educational explanation and simulated examples
    else {
      for (const paragraph of step.paragraphs || []) {
        content.push(createElement("p", paragraph));
      }

      if (step.example) {
        content.push(createElement("pre", step.example));
      }

      for (const paragraph of step.afterExample || []) {
        content.push(createElement("p", paragraph));
      }

      const buttons = document.createElement("div");
      buttons.className = "proposal-controls";

      if (index > 0) {
        buttons.append(
          createButton("Back", () => showStep(index - 1), true)
        );
      }

      buttons.append(
        createButton("Next Step", () => showStep(index + 1))
      );

      content.push(buttons);
    }

    lessonContent.replaceChildren(...content);
    lessonContent.hidden = false;
  }

  function startLesson(id) {
    const selectedLesson = LESSONS[id];

    if (!selectedLesson) {
      return;
    }

    currentLesson = selectedLesson;

    library.hidden = true;
    activeLessonPanel.hidden = false;
    activeLessonTitle.textContent = selectedLesson.title;

    showStep(0);
  }

  // Connect both Start Lesson buttons.
  library.querySelectorAll("button[data-lesson-id]").forEach(
    (button) => {
      button.addEventListener("click", () => {
        startLesson(button.dataset.lessonId);
      });
    }
  );

  // Return to the lesson selection screen.
  backToLessonsButton.addEventListener(
    "click",
    showLibrary
  );
}
