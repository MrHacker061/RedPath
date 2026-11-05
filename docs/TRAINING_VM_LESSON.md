# RP-SVC-001 training lesson

The **Investigate an Exposed FTP Service** card on `/lessons` is a typed-command practice exercise for the local RP-SVC-001 VM. Browser entries are checked against the lesson commands and reveal representative output. The page never executes a command or reads the VM's current state.

The VM source is kept outside this repository at `C:\Users\bocaj\Downloads\RedPath-Training-VM`. Its Vagrant state remains under `%LOCALAPPDATA%\RedPath\TrainingVM\RP-SVC-001`. The source directory is local and is not bundled with RedPath installs; another developer must obtain the approved VM separately.

From PowerShell in the VM source directory, run `./TrainingVM.ps1 create` and `./TrainingVM.ps1 health`. The target is `192.168.56.20` on a VirtualBox host-only network. From a lab machine attached to that network, run the commands shown in the lesson to see the actual output. The browser's representative output can differ from the VM's package banners.

The intended finding is unnecessary anonymous read-only FTP on port 21; SSH on port 22 is expected. After confirmation, use `./TrainingVM.ps1 remediate` on the Windows host and repeat the scoped scan. Use `./TrainingVM.ps1 reset -Force` to restore the exercise. Do not use bridged networking for this VM.
