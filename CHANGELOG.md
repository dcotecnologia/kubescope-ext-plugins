# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.1] - 2026-11-24

### Fixed

- The **Update** and **Uninstall** buttons and the same entries of the context menu are out of sight while the app is read-only, and come back with the write mode; **Details** stays by @danilogco

## [1.2.0] - 2026-11-24

### Changed

- The notice of an update or an uninstall is a `task` notice, so the notifications extension keeps it in the bell and the person chooses whether it is listed and told (it needs the SDK 1.10) by @danilogco

## [1.1.0] - 2026-11-24

### Added

- **Uninstall**, in the write mode, for one add-on or release or for many at once (the boxes of the rows): it shows the commands first and runs them one after the other, with `helm uninstall`, `aws eks delete-addon` or `az k8s-extension delete`, through the app; it needs the SDK 1.9 by @danilogco

### Changed

- With several rows checked, **Details** and **Update** are hidden, since they work on one row, and only **Uninstall** stays by @danilogco
- What is done is told by a notice of the system, not by a dialog that stands in the way by @danilogco

## [1.0.1] - 2026-11-24

### Fixed

- **Update** of a Helm release fills in the chart the release installed, not the name of the release, so a release called `external-secrets-op` is updated with the chart `external-secrets` by @danilogco

## [1.0.0] - 2026-11-24

### Added

- **Cluster Plugins**, the Plugins section of KubeScope as an extension: **Installed** lists the Amazon EKS add-ons, the Azure extensions, the Google Cloud add-ons and the Helm releases of the cluster, with their chart, app and latest versions, the last update and an origin filter, and updates them in the write mode; **Catalog** browses the Helm charts of Artifact Hub by @danilogco
- A click on a header sorts the add-ons, and a second one reverses it, by what the cells mean (ages, versions) by @danilogco

[Unreleased]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/releases/tag/v1.0.0
