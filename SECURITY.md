# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability. Use
[GitHub private vulnerability reporting](https://github.com/dcotecnologia/kubescope-ext-plugins/security/advisories/new)
for this repository, or write to the maintainers listed in `pyproject.toml`. We acknowledge a report
within a few days, tell you what we found, and credit you in the release notes if you want.

## Supported versions

Only the latest release receives fixes.

## What it is

An extension is Python code that runs inside KubeScope with the same rights as the app. Its permissions
(`kubescope-extension.toml`) catch mistakes and tell you what it does; they are **not a sandbox**. Read
[the security notes of the SDK](https://github.com/dcotecnologia/kubescope-sdk/blob/main/docs/permissions.md)
before you install any extension.

## Guarantees this project keeps

- It asks for the least permissions it needs, and the README says why it asks for each one.
- It reads clusters and accounts only through the services the app lends it, and changes nothing outside the write mode.
- It never stores or logs credentials or secrets, and it makes no network request of its own beyond what the README says.
- Every release is a tag; KubeScope installs what it recommends only if the files are the ones whose hash it pinned.
- **It changes a cluster only when you ask and only in the write mode.** **Update** shows the exact command first and runs it only after you confirm, through the app (`aws eks update-addon`, `helm upgrade` or `az k8s-extension update`, and nothing else). It installs nothing from the catalog: **Install** shows the `helm` commands for you to copy and run.
- **The Helm releases are read from their own Secret by the app.** The app reads the latest Secret of each release, decodes it in memory and hands the extension only the chart name, the chart version and the app version.
- **It asks AWS and Artifact Hub.** The Latest column runs `aws eks describe-addon-versions` (read only) for each EKS add-on and searches Artifact Hub (`artifacthub.io`, over HTTPS), sending the name of the chart of each Helm release; the answer is kept for ten minutes. The catalog asks the public Artifact Hub API for the text you typed, with a `User-Agent` that names the extension, and reads the logos from `artifacthub.io/image`. A failure leaves a dash.
- **It keeps nothing on disk.** What it lists is read each time and kept in memory.
