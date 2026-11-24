# KubeScope Plugins

[![CI](https://github.com/dcotecnologia/kubescope-ext-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/dcotecnologia/kubescope-ext-plugins/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.15](https://img.shields.io/badge/python-3.15-3776AB.svg?logo=python&logoColor=white)](pyproject.toml)
[![KubeScope extension](https://img.shields.io/badge/KubeScope-extension-326CE5.svg?logo=kubernetes&logoColor=white)](https://github.com/dcotecnologia/kubescope)

Plugins for [KubeScope](https://github.com/dcotecnologia/kubescope): the **add-ons** and **Helm releases** of the
cluster with their chart, app and latest versions, **updates** in the write mode, and a **catalog** of Helm charts
from [Artifact Hub](https://artifacthub.io).

It is an **extension** written against the [KubeScope SDK](https://github.com/dcotecnologia/kubescope-sdk)
and nothing else of the app. Install it in **Settings → Extensions**.

## What it does

A **Plugins** group in the **Monitoring** section of the side menu, with two pages:

- **Installed.** The Amazon EKS add-ons, the Azure AKS extensions, the Google Cloud GKE add-ons and the Helm
  releases of the cluster, with their status, **chart** version, **app** version, the **latest** version (an arrow
  says when a newer one is out), the source, the last update and the age. A selector filters by **origin** (Helm or
  the cluster) and a box searches every column.
- **Update.** In the write mode, right-click a row and choose **Update**: the dialog asks for what the update takes
  (a version for an EKS add-on or an AKS extension; the chart, repository, version and values for a Helm release),
  shows the exact command and, when you confirm, has KubeScope run it (`aws eks update-addon`,
  `az k8s-extension update` or `helm upgrade`).
- **Catalog.** The Helm charts of Artifact Hub as cards, with their version, repository and badges (official,
  verified publisher, CNCF). **Install** installs nothing: it shows the `helm` commands for you to copy and run.

## Permissions

| Permission | Why |
| ---------- | --- |
| `cluster.read` | Lists the add-ons and the Helm releases, and names the cluster of the context |
| `cluster.write` | Has the app run the update, only in the write mode and after you confirm |
| `aws.read` | Reads the versions EKS offers for an add-on and the version of the cluster |
| `subprocess` | The update runs `aws`, `az` or `helm` of this computer, through the app |
| `ui.page` | Adds its pages to the side menu |
| `ui.window` | Shows the messages |

It also asks the public Artifact Hub (`artifacthub.io`, over HTTPS) for the latest version of a chart and for the
catalog; see [SECURITY.md](SECURITY.md).

## Requirements

KubeScope 2.7 or newer (the extension API `0`) and the SDK 1.7 or newer, which the app brings. To update, `aws`,
`az` or `helm` has to be installed, and your account must be allowed to do it. To read the chart of a Helm release the
app needs `get` on `secrets`; without it the versions come from the labels of the release's workloads.

## Develop

```sh
make setup
make test FILE=tests/test_installed_page.py   # one file, without coverage
make lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT
