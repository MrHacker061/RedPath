// Browser practice mirrors RP-SVC-001. Nothing entered here runs on the VM.
export const TRAINING_VM_LESSON = {
  title: "Investigate an Exposed FTP Service",
  machine: { address: "Your lab machine" },
  target: { address: "192.168.56.20" },
  terminals: [[
    { step: 1, command: "nmap -sV -Pn -p 21,22 192.168.56.20", output: "PORT   STATE SERVICE VERSION\n21/tcp open  ftp     vsftpd\n22/tcp open  ssh     OpenSSH" },
    { step: 2, command: "curl --list-only ftp://192.168.56.20/", output: "README.txt" },
    { step: 3, command: "nmap -sV -Pn -p 21,22 192.168.56.20", output: "PORT   STATE  SERVICE\n21/tcp closed ftp\n22/tcp open   ssh" }
  ]],
  steps: [
    {
      label: "Lab boundary", title: "Meet the training target",
      paragraphs: [
        "RP-SVC-001 is your local, deliberately misconfigured VM. It uses the VirtualBox host-only address 192.168.56.20. SSH on port 22 is expected; anonymous, read-only FTP on port 21 is unnecessary.",
        "Start and check the VM from your RedPath-Training-VM folder with .\\TrainingVM.ps1 create and .\\TrainingVM.ps1 health. Keep its network host-only. The commands you type in this page produce simulated output; run them in your authorized lab terminal to observe the real VM."
      ],
      guide: "First, confirm the target is running and reachable on your private lab network. Browser practice does not connect to it.",
      hints: ["The VM README in the relocated folder has the setup and reset commands."]
    },
    {
      label: "Discover", title: "Scan the approved ports",
      paragraphs: ["Type an Nmap service scan limited to TCP ports 21 and 22 on 192.168.56.20. -Pn avoids relying on ping discovery. Read the state and service columns before drawing a conclusion."],
      command: "nmap -sV -Pn -p 21,22 192.168.56.20",
      commandLabel: "Kali command to scan ports 21 and 22",
      guide: "Enter the scan yourself. The lesson will reveal a representative result after you enter the expected command.",
      hints: ["Use nmap -sV -Pn, then -p 21,22, then the target address."]
    },
    {
      label: "Confirm", title: "Inspect the exposed service",
      paragraphs: ["The scan shows FTP and SSH open. Check the read-only FTP listing to confirm anonymous access without uploading, guessing passwords, or changing the target."],
      command: "curl --list-only ftp://192.168.56.20/",
      commandLabel: "Kali command to list anonymous FTP files",
      guide: "A directory listing is enough to confirm the exposure. Do not treat a version string alone as proof of a software vulnerability.",
      hints: ["Use curl --list-only with the ftp:// URL for the lab address."]
    },
    {
      label: "Remediate", title: "Close FTP and verify",
      paragraphs: ["On the Windows host, run .\\TrainingVM.ps1 remediate from the relocated VM folder. Then type the same limited Nmap scan below. The representative result shows FTP closed while SSH stays open. Run the scan in your real lab terminal to verify your own VM."],
      command: "nmap -sV -Pn -p 21,22 192.168.56.20",
      commandLabel: "Kali command to verify ports after remediation",
      guide: "Compare before and after. The intended change is port 21 closing while port 22 stays available.",
      hints: ["Repeat the exact scan from the Discover step after remediation."]
    },
    {
      label: "Knowledge check", title: "Knowledge Check",
      question: "Which finding should you report for RP-SVC-001?",
      choices: ["Anonymous FTP on 21/tcp is unnecessary for this host", "SSH on 22/tcp is always vulnerable", "Every open port should be exploited"],
      answer: "Anonymous FTP on 21/tcp is unnecessary for this host",
      correctFeedback: "Correct. The issue is unnecessary anonymous FTP exposure, supported by the scan and listing.",
      wrongFeedback: "Review what this host needs and what the two services expose.",
      guide: "Report only what the evidence supports. You can restore the exercise with .\\TrainingVM.ps1 reset -Force on the Windows host.",
      hints: ["SSH is expected here; FTP is the intentional misconfiguration."]
    }
  ],
  takeaways: ["Scope scans to the approved VM and ports", "Confirm service exposure with read-only evidence", "Report the unnecessary service, not an invented exploit", "Rescan after remediation"],
  findings: [
    { step: 1, title: "FTP and SSH answer on the target", detail: "The representative scan shows 21/tcp and 22/tcp open.", why: "SSH is expected for administration. FTP needs a reason to exist." },
    { step: 2, title: "Anonymous FTP permits read-only listing", detail: "The representative listing shows synthetic lab files without a login.", why: "Unnecessary anonymous access exposes information even when uploads are disabled." },
    { step: 3, title: "FTP closes after remediation", detail: "The representative rescan shows 21/tcp closed and 22/tcp open.", why: "A follow-up observation checks that the fix worked without removing expected SSH access." }
  ],
  questions: [
    { id: "why-ftp", step: 2, question: "Is an open FTP port an exploit?", answer: "No. This finding is an unnecessary service that allows anonymous read-only listing. The evidence supports an exposure and a configuration fix, not a claim of code execution." },
    { id: "reset-vm", step: 3, question: "How do I repeat the lab?", answer: "From your RedPath-Training-VM folder on the Windows host, run .\\TrainingVM.ps1 reset -Force, then .\\TrainingVM.ps1 health. The reset restores the intentional FTP exposure." }
  ],
  completion: "You practiced scoped discovery, read-only confirmation, and verification after closing an unnecessary service."
};

export function matchesTrainingCommand(input, expected) {
  return input.trim().replace(/\s+/g, " ") === expected;
}
