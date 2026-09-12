# RedPath Release-Ready MVP Design

## Goal

Produce an unsigned Windows development installer for RedPath whose normal
recommendation path uses the configured local Ollama model. The installer and
first-run setup must preserve RedPath's existing authorized-lab boundaries.

## Scope

This release slice will:

- select the existing `OllamaProvider` by default;
- retain its existing deterministic `RuleBasedProvider` fallback when Ollama
  is unavailable or returns invalid structured output;
- disclose the exact byte size of each pinned setup artifact before consent;
- build the pinned desktop executable and Inno Setup installer;
- smoke-test the executable and installer on this Windows 11 machine;
- record hashes and observed release evidence in the checklist.

It will not add cloud models, arbitrary model selection, exploitation,
credential testing, reverse shells, public-target support, automatic signing,
or automatic publication.

## Provider Flow

`redpath.app.create_app()` will construct the existing `OllamaProvider` as the
application provider. The provider already restricts traffic to
`127.0.0.1:11434`, requests schema-constrained output, validates the proposal
against the authorized session context, uses bounded timeouts, and falls back
to `RuleBasedProvider` on local provider failure.

Tests will prove that a newly created application selects Ollama, that the
fallback remains deterministic, and that tests can still replace the provider
with fakes without contacting a real model.

## Download Disclosure

The existing `Artifact` record will gain one required positive `size_bytes`
field. The pinned Ollama installer and Kali WSL artifact will use sizes verified
against their exact source URLs. Setup API responses will expose only the
pinned artifact name, version, and byte size needed for informed consent. The
frontend will render this metadata as literal text before repair/install
confirmation. No new metadata service or configuration layer will be added.

The downloader will continue enforcing HTTPS and SHA-256. If practical without
duplicating checks, it will also reject a completed transfer whose byte count
does not match the manifest.

## Packaging

The repository's pinned `PyInstaller 6.22.2` and `pywebview 6.2.1` dependencies
will build `dist/RedPath/RedPath.exe`. Inno Setup 6.3 or newer will build
`dist/installer/RedPath-Setup-0.1.0-x64.exe`. Build prerequisites may be
installed on this development machine, but they will not become runtime
prerequisites for end users.

The development artifact will remain unsigned. The release notes and checklist
must state that clearly and must not imply production signing or publication.

## Verification

Before the installer is called ready, the following evidence is required:

1. Python, frontend, Kali policy, desktop-build, and installer-policy tests pass.
2. The desktop executable builds and has a recorded SHA-256.
3. The installer builds and has a recorded SHA-256.
4. The installed app launches in its own window, binds only to loopback, and
   exposes the expected health endpoint.
5. First-run setup visibly discloses pinned transfer sizes before consent.
6. A local Ollama-backed recommendation is attempted when the configured model
   is available; fallback behavior is verified separately.
7. Default uninstall removes packaged files while preserving mutable RedPath,
   Ollama, and managed Kali data.

Checks that require a separate clean Windows 11 machine will remain explicitly
unverified if this host cannot provide that isolation. A failed or unavailable
gate will be reported rather than treated as passed.

## Rollback

The source rollback is a revert of this release branch. The local artifact
rollback is the normal RedPath uninstall, which preserves user and lab data by
default. No installer or release will be uploaded automatically.
