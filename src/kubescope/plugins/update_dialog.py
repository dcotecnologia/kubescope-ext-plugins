from collections.abc import Callable
from typing import Any

from kubescope.sdk import translate
from kubescope.sdk.errors import ClusterError

from kubescope.plugins import updates

AKS_KIND = "AksExtension"


class PluginUpdateDialog:
    """Asks for what an update needs and shows the exact command it will run.

    An EKS add-on takes a version (from the ones EKS offers) and what to
    do with the fields that were changed by hand; a Helm release takes
    the chart, where to read it from, a version and its values.
    Accepting it leaves the command in `arguments`; the page has the app
    run it.
    """

    def __init__(
        self,
        parent: Any,
        components: Any,
        context: str,
        row: Any,
        installed: str,
        latest: str,
        versions: list[str],
        repository: str = "",
        eks_target: list[str] | None = None,
        target: tuple[str, str] = ("", ""),
        chart: str = "",
    ) -> None:
        self.components = components
        self.context = context
        self.row = row
        self.arguments: list[str] = []
        self.is_eks = row.kind == "Addon"
        self.is_aks = row.kind == AKS_KIND
        self.eks_target = eks_target or []
        self.target = target  # the name and resource group of an AKS cluster
        rows: list[tuple[str, Any]] = [
            (
                translate("PluginUpdateDialog", "Installed"),
                components.label(installed),
            ),
        ]
        extra: list[Any] = []
        self._builder: Callable[[], list[str]]
        if self.is_eks or self.is_aks:
            self.eks_version = components.filter_select()
            self.eks_version.setEditable(True)
            self.eks_version.addItems(versions)
            if latest in versions:
                self.eks_version.setCurrentIndex(versions.index(latest))
            self.conflicts = components.filter_select()
            for option, text in (
                (
                    "NONE",
                    translate(
                        "PluginUpdateDialog", "Stop if a field was changed by hand"
                    ),
                ),
                (
                    "OVERWRITE",
                    translate(
                        "PluginUpdateDialog", "Overwrite the fields changed by hand"
                    ),
                ),
                (
                    "PRESERVE",
                    translate("PluginUpdateDialog", "Keep the fields changed by hand"),
                ),
            ):
                self.conflicts.addItem(text, option)
            rows.append(
                (
                    translate("PluginUpdateDialog", "Update to version"),
                    self.eks_version,
                )
            )
            if self.is_eks:  # only EKS decides what to do with the fields changed
                rows.append(
                    (
                        translate("PluginUpdateDialog", "If a field was changed"),
                        self.conflicts,
                    )
                )
            self.eks_version.currentTextChanged.connect(self._preview)
            self.conflicts.currentIndexChanged.connect(self._preview)
            self._builder = self._eks_arguments
        else:
            # the chart of a release is not named like the release: a release called
            # external-secrets-op is the chart external-secrets
            self.chart = components.text_field()
            self.chart.setText(chart or row.name)
            self.repository = components.text_field(
                translate("PluginUpdateDialog", "https://charts.example.com")
            )
            self.helm_version = components.filter_select()
            self.helm_version.setEditable(True)
            self.helm_version.addItems(versions)
            self.helm_version.setCurrentIndex(0 if versions else -1)
            self.repository.setText(repository)
            self.values_file = components.text_field(
                translate("PluginUpdateDialog", "none")
            )
            self.reuse = components.checkbox(
                translate("PluginUpdateDialog", "Keep the values the release has"),
                True,
            )
            rows += [
                (translate("PluginUpdateDialog", "Chart"), self.chart),
                (
                    translate("PluginUpdateDialog", "Repository"),
                    self.repository,
                ),
                (
                    translate("PluginUpdateDialog", "Chart version"),
                    self.helm_version,
                ),
                (
                    translate("PluginUpdateDialog", "Values file"),
                    self.values_file,
                ),
                ("", self.reuse),
            ]
            for edit in (self.chart, self.repository, self.values_file):
                edit.textChanged.connect(self._preview)
            self.helm_version.currentTextChanged.connect(self._preview)
            self.reuse.toggled.connect(self._preview)
            self._builder = self._helm_arguments
            extra.append(
                components.label(
                    translate(
                        "PluginUpdateDialog",
                        "Helm does not keep where a chart came from: give the chart "
                        "as repo/name or oci://..., or its name with the repository "
                        "address.",
                    ),
                    wrap=True,
                )
            )
        self.command = components.command_box(height=90)
        self.problem = components.label(variant="muted", wrap=True)
        self.update_button = components.button(
            translate("PluginUpdateDialog", "Update"), "primary"
        )
        cancel = components.button(translate("PluginUpdateDialog", "Cancel"))
        cancel.setDefault(True)
        self.dialog = components.dialog(
            parent,
            translate("PluginUpdateDialog", "Update {name}").format(name=row.name),
            components.column(
                components.form(rows),
                *extra,
                components.label(
                    translate("PluginUpdateDialog", "This command will run:")
                ),
                self.command,
                self.problem,
            ),
            [cancel, self.update_button],
            width=640,
        )
        self.update_button.clicked.connect(self.dialog.accept)
        cancel.clicked.connect(self.dialog.reject)
        self._preview()

    def exec(self) -> bool:
        return bool(self.dialog.exec())

    def _eks_arguments(self) -> list[str]:
        if self.is_aks:
            return updates.aks_update_arguments(
                *self.target, self.row.name, self.eks_version.currentText().strip()
            )
        return updates.eks_update_arguments(
            self.eks_target,
            self.row.name,
            self.eks_version.currentText().strip(),
            self.conflicts.currentData(),
        )

    def _helm_arguments(self) -> list[str]:
        return updates.helm_upgrade_arguments(
            self.context,
            self.row.namespace,
            self.row.name,
            self.chart.text().strip(),
            self.helm_version.currentText().strip(),
            self.repository.text().strip(),
            self.reuse.isChecked(),
            self.values_file.text().strip(),
        )

    def _preview(self, *_args: object) -> None:
        try:
            arguments = self._builder()
        except ClusterError as error:
            self.arguments = []
            self.command.setPlainText("")
            self.problem.setText(str(error))
            self.update_button.setEnabled(False)
            return
        self.command.setPlainText(updates.commands(arguments))
        program = arguments[0]
        if updates.program_missing(program):  # shown, but it cannot run here
            self.arguments = []
            self.problem.setText(
                translate(
                    "PluginUpdateDialog",
                    "{program} is not installed, so KubeScope cannot run this. "
                    "Install it, or copy the command and run it where it is.",
                ).format(program=program)
            )
            self.update_button.setEnabled(False)
            return
        self.arguments = arguments
        self.problem.setText("")
        self.update_button.setEnabled(True)
