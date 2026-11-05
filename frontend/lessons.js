
/*
 * RedPath beginner lessons.
 * All terminal examples are simulated.
 * No real commands or scans are executed.
 *
 * Each terminal entry and finding names the step that reveals it, so the
 * workspace fills in as the student moves through the lesson.
 */

const SIMULATED_KALI = { address: "10.0.2.15" };

export const LESSONS = {
  "network-scanning": {
    title: "Introduction to Network Scanning",
    machine: SIMULATED_KALI,
    target: { address: "192.168.56.20" },
    terminals: [
      [
        {
          step: 0,
          command: "ip a",
          output:
            "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n" +
            "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n" +
            "    inet 127.0.0.1/8 scope host lo\n" +
            "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP\n" +
            "    link/ether 08:00:27:3a:7f:12 brd ff:ff:ff:ff:ff:ff\n" +
            "    inet 10.0.2.15/24 brd 10.0.2.255 scope global dynamic eth0"
        },
        {
          step: 0,
          command: "ping -c 4 192.168.56.20",
          output:
            "PING 192.168.56.20 (192.168.56.20) 56(84) bytes of data.\n" +
            "64 bytes from 192.168.56.20: icmp_seq=1 ttl=64 time=0.72 ms\n" +
            "64 bytes from 192.168.56.20: icmp_seq=2 ttl=64 time=0.49 ms\n" +
            "64 bytes from 192.168.56.20: icmp_seq=3 ttl=64 time=0.52 ms\n" +
            "64 bytes from 192.168.56.20: icmp_seq=4 ttl=64 time=0.51 ms\n\n" +
            "--- 192.168.56.20 ping statistics ---\n" +
            "4 packets transmitted, 4 received, 0% packet loss, time 3004ms"
        }
      ],
      [
        {
          step: 1,
          command: "nmap -sV 192.168.56.20",
          output:
            "Starting Nmap 7.94 ( https://nmap.org )\n" +
            "Nmap scan report for 192.168.56.20\n" +
            "Host is up (0.00051s latency).\n" +
            "Not shown: 997 filtered tcp ports (no-response)\n\n" +
            "PORT     STATE    SERVICE  VERSION\n" +
            "22/tcp   open     ssh      OpenSSH 8.9p1 Ubuntu\n" +
            "80/tcp   closed   http\n" +
            "443/tcp  closed   https\n\n" +
            "Nmap done: 1 IP address (1 host up) scanned in 7.32 seconds"
        }
      ]
    ],
    steps: [
      {
        label: "Scanning basics",
        title: "Understanding Network Scanning",
        paragraphs: [
          "Network scanning identifies open ports and services on an authorized computer or network. It helps you understand what a system exposes.",
          "A port is a numbered communication endpoint. Port 22 is commonly used for SSH, and port 80 is commonly used for HTTP.",
          "Before scanning, check your own address and whether the target answers. In Terminal 1, ip a shows your Kali machine's address (10.0.2.15) and ping shows the practice target replying.",
          "Only scan systems you own or have explicit permission to test."
        ],
        guide:
          "Welcome! Terminal 1 shows two quick checks you make before any scan: which address your Kali machine uses, and whether the practice target answers. Everything here is simulated.",
        hints: [
          "Under eth0 in Terminal 1, the line starting with inet shows your Kali address.",
          "0% packet loss means the target answered every ping."
        ]
      },
      {
        label: "Scan results",
        title: "Understanding Scan Results",
        paragraphs: [
          "Terminal 2 shows simulated results from a service scan of the practice target. No real scan is performed in this lesson.",
          "Port 22 is open and associated with SSH. Ports 80 and 443 are closed in this example.",
          "An open port does not automatically mean that a system is vulnerable."
        ],
        guide:
          "The scan in Terminal 2 has finished. I've added what it shows to Findings.",
        hints: [
          "Read the STATE column first: open means a service answered on that port.",
          "The VERSION column tells you what to research next."
        ]
      },
      {
        label: "Knowledge check",
        title: "Knowledge Check",
        question:
          "Based on the previous scan results, which TCP port was open?",
        choices: ["22/tcp", "80/tcp", "443/tcp"],
        answer: "22/tcp",
        correctFeedback:
          "Correct! Port 22 was open and associated with SSH.",
        wrongFeedback:
          "Not quite! Review the simulated scan results and try again.",
        guide:
          "Time for a quick check. The answer is in Terminal 2.",
        hints: [
          "Look for the row in Terminal 2 whose STATE is open."
        ]
      }
    ],
    takeaways: [
      "Open ports reveal available services",
      "Service versions tell you what to research",
      "An open port is not proof of a vulnerability",
      "Only scan systems you are authorized to test"
    ],
    findings: [
      {
        step: 0,
        title: "192.168.56.20 is reachable",
        detail:
          "The practice target replied to 4 of 4 pings, so it is up and reachable from your Kali machine.",
        why:
          "A host that answers is ready to scan. Some hosts block ping and are still up, so ping is a quick check, not proof."
      },
      {
        step: 1,
        title: "Port 22 (SSH) is open on 192.168.56.20",
        detail:
          "The target is running an SSH service (OpenSSH 8.9p1). SSH provides secure remote access to the system.",
        why:
          "Open services increase the attack surface. Note the version, check it for known vulnerabilities, and confirm the service is meant to be exposed.",
        followUp: "ssh-enumeration"
      },
      {
        step: 1,
        title: "Ports 80 and 443 are closed",
        detail:
          "The target answered on these ports, but no web service is listening.",
        why:
          "Closed ports are still evidence: they show the host is reachable and what it is not running."
      }
    ],
    questions: [
      {
        id: "ip-a",
        step: 0,
        question: "What does ip a show?",
        answer:
          "ip a lists your machine's network interfaces. lo is the loopback interface (127.0.0.1) the system uses to talk to itself. eth0 is the network card, and its inet line, 10.0.2.15/24, is the address your Kali machine uses on the lab network."
      },
      {
        id: "why-ping",
        step: 0,
        question: "Why ping before scanning?",
        answer:
          "Ping confirms the target is up, reachable from your machine, and that you typed the right address. A host that ignores ping may still be up, because firewalls often block it."
      },
      {
        id: "nmap-output",
        step: 1,
        question: "What does this nmap output mean?",
        answer:
          "Each row is a port nmap checked. STATE says whether a service answered (open) or the port refused the connection (closed). SERVICE is nmap's best guess at what runs there, and VERSION is the software it identified: OpenSSH 8.9p1 on port 22."
      },
      {
        id: "ssh-enumeration",
        step: 1,
        question: "Tell me more about SSH enumeration",
        answer:
          "Enumeration means collecting more detail about a service you found. For SSH that usually means confirming the version, checking which login methods it accepts, and looking up advisories for that version. In RedPath you would do this through an approved action in an authorized lab session."
      },
      {
        id: "risky",
        step: 1,
        question: "Are these results risky?",
        answer:
          "Not by themselves. An open SSH port is normal for a server that is managed remotely. The risk depends on the version, how logins are protected (keys rather than passwords, for example), and whether the service should be exposed at all."
      }
    ],
    completion:
      "You learned about ports, services, and interpreting basic network scan results."
  },

  "linux-commands": {
    title: "Introduction to Linux Commands",
    machine: SIMULATED_KALI,
    target: null,
    terminals: [
      [
        { step: 0, command: "whoami", output: "kali" },
        { step: 0, command: "pwd", output: "/home/kali" }
      ],
      [
        { step: 1, command: "ls", output: "labs  notes.txt" },
        {
          step: 1,
          command: "ls -l",
          output:
            "total 8\n" +
            "drwxr-xr-x 2 kali kali 4096 Apr 26 15:40 labs\n" +
            "-rw-r--r-- 1 kali kali  212 Apr 26 15:38 notes.txt"
        }
      ]
    ],
    steps: [
      {
        label: "Terminal basics",
        title: "Understanding the Linux Terminal",
        paragraphs: [
          "The Linux terminal lets you interact with the operating system by entering text commands.",
          "In Terminal 1, whoami prints the current username (kali) and pwd prints your current directory (/home/kali).",
          "In RedPath, practice commands only in a controlled, authorized learning environment."
        ],
        guide:
          "Welcome! Terminal 1 shows two commands that answer \"who am I?\" and \"where am I?\". These are simulated examples, so nothing actually runs.",
        hints: [
          "The line after each command is its output.",
          "The ~ in the prompt is shorthand for your home directory, /home/kali."
        ]
      },
      {
        label: "Listing files",
        title: "Reading Terminal Output",
        paragraphs: [
          "Terminal 2 shows ls, which lists the files and folders in your current directory. These are simulated examples. No commands are actually executed.",
          "ls -l shows the same items in a long format: permissions, owner, size, and date.",
          "A line that starts with d is a directory, so labs is a directory and notes.txt is a file."
        ],
        guide:
          "Terminal 2 now lists what is in your home directory. I've added what it shows to Findings.",
        hints: [
          "Compare the first character of each ls -l line: d means directory, - means regular file."
        ]
      },
      {
        label: "Knowledge check",
        title: "Knowledge Check",
        question:
          "Which Linux command displays your current directory?",
        choices: ["ls", "pwd", "whoami"],
        answer: "pwd",
        correctFeedback:
          "Correct! pwd prints the current working directory.",
        wrongFeedback:
          "Not quite! Think about which command prints the working directory.",
        guide:
          "Time for a quick check. Look back at Terminal 1 if you need a reminder.",
        hints: [
          "Which command printed /home/kali?"
        ]
      }
    ],
    takeaways: [
      "whoami shows which account you are using",
      "pwd shows where you are",
      "ls lists what is in a directory",
      "Practice only in an authorized environment"
    ],
    findings: [
      {
        step: 0,
        title: "You are logged in as kali",
        detail: "whoami printed kali, so commands run as the kali user.",
        why: "Your account decides what you are allowed to read, change, and run."
      },
      {
        step: 0,
        title: "Your current directory is /home/kali",
        detail: "pwd printed /home/kali, the kali user's home directory.",
        why: "Commands that use relative paths act on the current directory, so check it before you create or delete files."
      },
      {
        step: 1,
        title: "Home contains labs and notes.txt",
        detail: "ls -l shows labs is a directory and notes.txt is a 212-byte file.",
        why: "Listing a directory is the first step to finding the files a task needs."
      }
    ],
    questions: [
      {
        id: "tilde",
        step: 0,
        question: "What does the ~ in the prompt mean?",
        answer:
          "~ is shorthand for your home directory. For the kali user that is /home/kali, which is why pwd printed that path."
      },
      {
        id: "whoami",
        step: 0,
        question: "Why does whoami matter?",
        answer:
          "Linux decides what you may read, change, or run based on your user account. whoami confirms which account the terminal is using before you do anything else."
      },
      {
        id: "permissions",
        step: 1,
        question: "What do the letters in ls -l mean?",
        answer:
          "The first character is the type: d for a directory, - for a regular file. The next nine are read (r), write (w), and execute (x) permissions for the owner, the group, and everyone else."
      },
      {
        id: "hidden-files",
        step: 1,
        question: "How do I see hidden files?",
        answer:
          "Files whose names start with a dot are hidden from plain ls. ls -a shows them, and ls -la combines that with the long format."
      }
    ],
    completion:
      "You learned how pwd, ls, and whoami help you understand a Linux terminal session."
  }
};

const WELCOME =
  "Hi! I'm your lesson guide. Pick a lesson to start. I'll explain the simulated output, collect findings, and give hints when you're stuck.";

export function formatElapsed(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = String(Math.floor(seconds / 60) % 60).padStart(2, "0");
  return `${Math.floor(seconds / 3600)}:${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function initializeLessons() {
  const selectors = {
    library: "#lesson-library",
    libraryTitle: "#lesson-library-title",
    activeLesson: "#active-lesson",
    activeTitle: "#active-lesson-title",
    subtitle: "#lab-subtitle",
    machineAddress: "#lab-machine-address",
    targetAddress: "#lab-target-address",
    exit: "#exit-lesson",
    timer: "#lesson-timer",
    terminals: "#lesson-terminals",
    steps: "#lesson-steps",
    progress: "#lesson-progress",
    whyToggle: "#why-toggle",
    whyBody: "#why-panel-body",
    content: "#lesson-content",
    takeaways: "#lesson-takeaways",
    messages: "#guide-messages",
    questions: "#guide-questions",
    findingsList: "#findings-list",
    findingsCount: "#findings-count",
    hints: "#hints-content"
  };

  const ui = {};

  for (const [name, selector] of Object.entries(selectors)) {
    ui[name] = document.querySelector(selector);

    if (!ui[name]) {
      return;
    }
  }

  const guideTabs = [...document.querySelectorAll('.assistant-tabs [role="tab"]')];
  const defaultSubtitle = ui.subtitle.textContent;

  let lessonId = null;
  let lesson = null;
  let current = 0;
  let reached = 0;
  let completed = false;
  let asked = new Set();
  let timerId = null;

  function createElement(tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text;

    if (className) {
      element.className = className;
    }

    return element;
  }

  function createButton(text, onClick, className) {
    const button = createElement("button", text, className);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  function createPrompt() {
    const prompt = document.createDocumentFragment();
    prompt.append(
      createElement("span", "kali@kali", "prompt-user"),
      ":",
      createElement("span", "~", "prompt-path"),
      "$ "
    );
    return prompt;
  }

  // Timer

  function startTimer() {
    clearInterval(timerId);
    const startedAt = Date.now();
    ui.timer.textContent = formatElapsed(0);
    timerId = setInterval(() => {
      ui.timer.textContent = formatElapsed(Date.now() - startedAt);
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerId);
    timerId = null;
  }

  // Lesson guide panel

  function selectTab(tab, moveFocus = false) {
    for (const other of guideTabs) {
      const selected = other === tab;
      other.setAttribute("aria-selected", String(selected));
      other.tabIndex = selected ? 0 : -1;
      document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
    }

    if (moveFocus) {
      tab.focus();
    }
  }

  function addMessage(content, className = "") {
    const message = document.createElement("article");
    message.className = `guide-message ${className}`.trim();

    if (typeof content === "string") {
      message.append(createElement("p", content));
    } else {
      message.append(...content);
    }

    ui.messages.append(message);
    ui.messages.scrollTop = ui.messages.scrollHeight;
    return message;
  }

  function addFindingCard(finding) {
    const label = createElement("p", "Observed Finding", "finding-label");
    label.prepend(createElement("span", "", "finding-icon"));

    const content = [
      label,
      createElement("h3", finding.title),
      createElement("p", finding.detail),
      createElement("p", "Why it matters:", "finding-why"),
      createElement("p", finding.why)
    ];

    const followUp = lesson.questions.find((entry) => entry.id === finding.followUp);

    if (followUp) {
      const button = createButton(followUp.question, () => ask(followUp.id), "guide-followup");
      button.dataset.questionId = followUp.id;
      button.disabled = asked.has(followUp.id);

      const icon = createElement("span", "↗", "followup-icon");
      icon.setAttribute("aria-hidden", "true");
      button.prepend(icon);
      content.push(button);
    }

    addMessage(content, "finding-card");
  }

  // Guide messages and findings for a step the student has just reached.
  function announceStep(index) {
    const step = lesson.steps[index];

    if (step.guide) {
      addMessage(step.guide);
    }

    lesson.findings
      .filter((finding) => finding.step === index)
      .forEach(addFindingCard);
  }

  function ask(id) {
    const entry = lesson?.questions.find((question) => question.id === id);

    if (!entry || asked.has(id)) {
      return;
    }

    asked.add(id);
    addMessage(entry.question, "from-student");
    addMessage(entry.answer);

    ui.messages
      .querySelectorAll(`[data-question-id="${id}"]`)
      .forEach((button) => { button.disabled = true; });

    renderQuestions();
    (ui.questions.querySelector("button") || ui.messages).focus();
  }

  function renderQuestions() {
    const followUps = new Set(lesson?.findings.map((finding) => finding.followUp));
    const available = lesson
      ? lesson.questions.filter((entry) =>
        entry.step <= reached && !asked.has(entry.id) && !followUps.has(entry.id))
      : [];

    // Suggest at most three, newest step first, so the chat keeps its room.
    available.sort((a, b) => b.step - a.step);

    ui.questions.replaceChildren(
      ...available.slice(0, 3).map((entry) =>
        createButton(entry.question, () => ask(entry.id), "guide-question"))
    );
  }

  function renderFindings() {
    const found = lesson
      ? lesson.findings.filter((finding) => finding.step <= reached)
      : [];

    ui.findingsCount.textContent = String(found.length);
    ui.findingsCount.hidden = found.length === 0;

    if (!found.length) {
      ui.findingsList.replaceChildren(
        createElement("li", "No findings yet. Start a lesson to see what the simulated output reveals.", "guide-empty")
      );
      return;
    }

    ui.findingsList.replaceChildren(...found.map((finding) => {
      const item = document.createElement("li");
      item.append(
        createElement("h3", finding.title),
        createElement("p", finding.detail),
        createElement("p", finding.why, "finding-why-text")
      );
      return item;
    }));
  }

  function renderHints() {
    const step = lesson?.steps[current];

    if (!step) {
      ui.hints.replaceChildren(
        createElement("p", lesson ? "You finished this lesson. No hints needed!" : "Start a lesson to see hints.", "guide-empty")
      );
      return;
    }

    const list = document.createElement("ol");
    list.className = "hint-list";
    list.append(...step.hints.map((hint) => createElement("li", hint)));

    ui.hints.replaceChildren(
      createElement("p", `Hints for step ${current + 1}: ${step.title}`, "hint-heading"),
      list
    );
  }

  // Workspace

  function renderTerminals() {
    const screens = [];

    ui.terminals.replaceChildren(...lesson.terminals.map((entries, index) => {
      const visible = entries.filter((entry) => entry.step <= reached);
      const terminal = document.createElement("article");
      terminal.className = "terminal-window";

      if (visible.some((entry) => entry.step === current)) {
        terminal.dataset.active = "true";
      }

      const titleBar = document.createElement("div");
      titleBar.className = "terminal-titlebar";

      const title = createElement("h3", "kali@kali: ~");
      title.prepend(createElement("span", `Terminal ${index + 1} `, "visually-hidden"));

      const controls = document.createElement("span");
      controls.className = "window-controls";
      controls.setAttribute("aria-hidden", "true");
      controls.append(
        createElement("span", "", "control-minimize"),
        createElement("span", "", "control-maximize"),
        createElement("span", "", "control-close")
      );

      titleBar.append(title, controls);

      const screen = document.createElement("pre");
      screen.className = "terminal-screen";
      screen.tabIndex = 0;
      screen.setAttribute("aria-label", `Terminal ${index + 1} simulated output`);

      if (!visible.length) {
        screen.append(createElement("span", `# Output appears in step ${entries[0].step + 1}.\n`, "terminal-comment"));
      }

      for (const entry of visible) {
        const block = createElement("span", "", entry.step === current ? "terminal-new" : "");
        block.append(createPrompt(), `${entry.command}\n${entry.output}\n\n`);
        screen.append(block);
      }

      const cursor = createElement("span", "", "terminal-cursor");
      cursor.setAttribute("aria-hidden", "true");
      screen.append(createPrompt(), cursor);
      screens.push(screen);

      terminal.append(titleBar, screen);
      return terminal;
    }));

    for (const screen of screens) {
      screen.scrollTop = screen.scrollHeight;
    }
  }

  function renderSteps() {
    const total = lesson.steps.length;

    ui.steps.replaceChildren(...lesson.steps.map((step, index) => {
      const item = document.createElement("li");
      const button = createButton(`${index + 1}. ${step.label}`, () => showStep(index, true), "step-tab");

      if (index === current) {
        button.setAttribute("aria-current", "step");
      }

      if (index < reached || completed) {
        button.dataset.done = "true";
      }

      item.append(button);
      return item;
    }));

    ui.progress.textContent = current === total
      ? `Lesson complete — ${total} of ${total} steps finished`
      : `Step ${current + 1} of ${total}`;
  }

  function stepHeading(text) {
    const heading = createElement("h4", text);
    heading.tabIndex = -1;
    return heading;
  }

  function explanationContent(step, index) {
    const controls = document.createElement("div");
    controls.className = "lesson-controls";

    if (index > 0) {
      controls.append(createButton("Back", () => showStep(index - 1, true), "secondary-button"));
    }

    controls.append(createButton("Next Step", () => showStep(index + 1, true)));

    return [
      stepHeading(`Step ${index + 1}: ${step.title}`),
      ...step.paragraphs.map((paragraph) => createElement("p", paragraph)),
      controls
    ];
  }

  function quizContent(step, index) {
    const total = lesson.steps.length;
    const form = document.createElement("form");
    const fieldset = document.createElement("fieldset");

    fieldset.append(createElement("legend", "Select one answer:"));

    for (const choice of step.choices) {
      const label = document.createElement("label");
      const input = document.createElement("input");

      input.type = "radio";
      input.name = "lesson-answer";
      input.value = choice;

      label.append(input, document.createTextNode(` ${choice}`));
      fieldset.append(label);
    }

    const feedback = createElement("p", "", "quiz-feedback");
    feedback.setAttribute("role", "status");

    const buttons = document.createElement("div");
    buttons.className = "lesson-controls";

    const checkButton = createElement("button", "Check Answer");
    checkButton.type = "submit";

    buttons.append(
      createButton("Back", () => showStep(index - 1, true), "secondary-button"),
      checkButton
    );

    const completeButton = createButton("Complete Lesson", () => {
      const selected = form.querySelector('input[name="lesson-answer"]:checked');

      if (selected?.value === step.answer) {
        showStep(total, true);
      }
    }, "complete-button");

    completeButton.hidden = true;

    // Reset feedback if the student changes answers.
    fieldset.addEventListener("change", () => {
      feedback.textContent = "";
      feedback.dataset.state = "";
      completeButton.hidden = true;
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();

      const selected = form.querySelector('input[name="lesson-answer"]:checked');

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

    form.append(fieldset, buttons, feedback, completeButton);

    return [
      stepHeading(`Step ${index + 1}: ${step.title}`),
      createElement("p", step.question),
      form
    ];
  }

  function completionContent() {
    const controls = document.createElement("div");
    controls.className = "lesson-controls";

    const labLink = createElement("a", "Start an authorized lab session", "button-link secondary-button");
    labLink.href = "/#lab";

    controls.append(
      createButton("Restart Lesson", () => startLesson(lessonId)),
      createButton("Choose Another Lesson", showLibrary, "secondary-button"),
      labLink
    );

    return [
      stepHeading("Lesson Complete!"),
      createElement("p", `Congratulations! You completed ${lesson.title}.`),
      createElement("p", lesson.completion),
      createElement("p", "Continue practicing only in an authorized lab environment."),
      controls
    ];
  }

  function setWhyExpanded(expanded) {
    ui.whyToggle.setAttribute("aria-expanded", String(expanded));
    ui.whyBody.hidden = !expanded;
  }

  function showStep(index, moveFocus = false) {
    if (!lesson) {
      return;
    }

    const total = lesson.steps.length;
    const finished = index === total;

    current = index;

    while (reached < Math.min(index, total - 1)) {
      reached += 1;
      announceStep(reached);
    }

    if (finished && !completed) {
      completed = true;
      stopTimer();
      addMessage(`Nice work! You finished ${lesson.title} in ${ui.timer.textContent}.`);
    }

    const step = lesson.steps[index];

    ui.content.replaceChildren(...(
      finished ? completionContent()
        : step.question ? quizContent(step, index)
          : explanationContent(step, index)
    ));

    renderSteps();
    renderTerminals();
    renderFindings();
    renderHints();
    renderQuestions();
    setWhyExpanded(true);

    if (moveFocus) {
      // Each step adds terminal output, so bring the terminals back into view.
      ui.activeLesson.scrollIntoView({ block: "start" });
      ui.content.querySelector("h4").focus({ preventScroll: true });
    }
  }

  function startLesson(id) {
    const selectedLesson = LESSONS[id];

    if (!selectedLesson) {
      return;
    }

    lessonId = id;
    lesson = selectedLesson;
    current = 0;
    reached = 0;
    completed = false;
    asked = new Set();

    ui.library.hidden = true;
    ui.activeLesson.hidden = false;
    ui.exit.hidden = false;
    ui.activeTitle.textContent = lesson.title;
    ui.subtitle.textContent = lesson.title;
    ui.machineAddress.textContent = lesson.machine.address;
    ui.targetAddress.textContent = lesson.target?.address ?? "Not used in this lesson";
    ui.takeaways.replaceChildren(...lesson.takeaways.map((takeaway) => createElement("li", takeaway)));

    ui.messages.replaceChildren();
    selectTab(guideTabs[0]);
    announceStep(0);
    startTimer();
    showStep(0, true);
  }

  function showLibrary() {
    const wasActive = lesson !== null;

    lessonId = null;
    lesson = null;
    stopTimer();

    ui.timer.textContent = formatElapsed(0);
    ui.activeLesson.hidden = true;
    ui.library.hidden = false;
    ui.exit.hidden = true;
    ui.subtitle.textContent = defaultSubtitle;
    ui.machineAddress.textContent = "No lesson selected";
    ui.targetAddress.textContent = "No lesson selected";
    ui.content.replaceChildren();

    ui.messages.replaceChildren();
    addMessage(WELCOME);
    renderFindings();
    renderHints();
    renderQuestions();

    if (wasActive) {
      ui.libraryTitle.focus();
    }
  }

  guideTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      const offset = { ArrowRight: 1, ArrowLeft: -1 }[event.key];

      if (offset) {
        event.preventDefault();
        selectTab(guideTabs[(index + offset + guideTabs.length) % guideTabs.length], true);
      }
    });
  });

  ui.library.querySelectorAll("button[data-lesson-id]").forEach((button) => {
    button.addEventListener("click", () => startLesson(button.dataset.lessonId));
  });

  ui.whyToggle.addEventListener("click", () => {
    setWhyExpanded(ui.whyToggle.getAttribute("aria-expanded") !== "true");
  });

  ui.exit.addEventListener("click", showLibrary);

  showLibrary();
}
