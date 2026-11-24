# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.1] - 2026-11-24

### Fixed

- **Update** of a Helm release fills in the chart the release installed, not the name of the release, so a release called `external-secrets-op` is updated with the chart `external-secrets` by @danilogco

## [1.0.0] - 2026-11-24

### Added

- **Cluster Plugins**, the Plugins section of KubeScope as an extension: **Installed** lists the Amazon EKS add-ons, the Azure extensions, the Google Cloud add-ons and the Helm releases of the cluster, with their chart, app and latest versions, the last update and an origin filter, and updates them in the write mode; **Catalog** browses the Helm charts of Artifact Hub by @danilogco
- A click on a header sorts the add-ons, and a second one reverses it, by what the cells mean (ages, versions) by @danilogco

[Unreleased]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/releases/tag/v1.0.0
