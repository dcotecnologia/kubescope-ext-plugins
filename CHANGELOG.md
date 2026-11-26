# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.5.0] - 2026-11-25

### Added

- The manifest says the newest KubeScope the extension works with (`max_app`, 3.0.0), so a KubeScope newer than that neither installs nor offers it, and keeps the version made for it; it needs KubeScope 2.10 and the SDK 1.13 (`Cluster.helm_chart_repository`) by @danilogco

### Fixed

- A Helm release whose chart is not at Artifact Hub no longer shows the version of another chart of the same name as its latest (the EFS CSI driver showed 0.1.0), and a release that says its repository (label `kubescope.dev/chart-repo`) has its latest version read from the `index.yaml` of that repository by @danilogco

## [1.4.1] - 2026-11-25

### Fixed

- The tests cover the two dialogs of the extension (whether they were accepted), so the coverage of the continuous integration is whole again and the release is published by @danilogco

## [1.4.0] - 2026-11-25

### Added

- The catalog can be narrowed to the charts of an **Official** publisher, of a **Verified publisher** or of a **CNCF** project, and ordered by **Most relevant**, **Most starred** or **Recently updated**; a click on a filter searches again by @danilogco

### Changed

- The search of the catalog keeps the width of a search box and its button the width of a button, with the filters under them, instead of a button that filled the page by @danilogco
- The extension imports nothing from `PySide6`, in its code or in its tests: its page is a plain object that holds its widget, and every widget, timer, icon, text and test helper comes from the SDK (`ctx.ui.components`, `translate`) by @danilogco
- The page is built with the elements of the app, through `ctx.ui.components` (SDK 1.12 and KubeScope 2.9): its table, the sorting by a click on a header, the badges, the buttons, the search box and the selects and fields, so it has no copy of them by @danilogco

## [1.3.0] - 2026-11-25

### Added

- A row with a newer version available shows the status **Outdated**, in the amber badge by @danilogco

### Changed

- The headers of the table are centered, the texts of the cells stay at the left by @danilogco

- Every cell and header of the table fits its column: a text that is too long is cut with an ellipsis, and the cell tip shows it whole by @danilogco

- The origin column (Helm, EKS...) is drawn as a badge, like the status by @danilogco

- A Helm release that is deployed shows the status **Active**, like the add-ons of the cloud, instead of **Deployed** by @danilogco

- The status badges all have the width of their column, so they line up by @danilogco

### Fixed

- The latest version of a Helm release no longer comes from a different chart of the same name: every chart of that name is checked for the installed version, not only the first five (Loki 7.5.0 now resolves to 7.7.0, not 21.6.0) by @danilogco

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

[Unreleased]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/dcotecnologia/kubescope-ext-plugins/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-ext-plugins/releases/tag/v1.0.0
