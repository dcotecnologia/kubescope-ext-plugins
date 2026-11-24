from kubescope.plugins import updates
from kubescope.plugins.update_dialog import AKS_KIND, PluginUpdateDialog
from tests.conftest import resource

TARGET = ["--cluster-name", "prod", "--region", "sa-east-1"]


def present(monkeypatch, missing=False):
    monkeypatch.setattr(updates, "program_missing", lambda _p: missing)


def test_an_eks_add_on_asks_for_a_version_and_what_to_do_with_changed_fields(
    monkeypatch,
) -> None:
    present(monkeypatch)
    row = resource("Addon", "vpc-cni", "", ("ACTIVE", "—", "v1", "EKS", "1d"))
    dialog = PluginUpdateDialog(None, "prod", row, "v1", "v3", ["v3", "v2"], "", TARGET)
    assert dialog.eks_version.currentText() == "v3"  # the latest is selected
    assert dialog.arguments[:3] == ["aws", "eks", "update-addon"]
    dialog.conflicts.setCurrentIndex(dialog.conflicts.findData("OVERWRITE"))
    assert "OVERWRITE" in dialog.arguments
    assert dialog.command.toPlainText().startswith("aws eks update-addon")


def test_the_latest_that_eks_does_not_offer_is_not_selected(monkeypatch) -> None:
    present(monkeypatch)
    row = resource("Addon", "vpc-cni", "", ("ACTIVE", "—", "v1", "EKS", "1d"))
    dialog = PluginUpdateDialog(None, "prod", row, "v1", "—", ["v3"], "", TARGET)
    assert dialog.eks_version.currentText() == "v3"  # the first offered


def test_an_aks_extension_asks_for_a_version_and_builds_the_az_command(
    monkeypatch,
) -> None:
    present(monkeypatch)
    row = resource(AKS_KIND, "flux", "", ("ok", "—", "1", "AKS", "1d"))
    dialog = PluginUpdateDialog(
        None, "aks", row, "1", "—", [], "", [], ("aks-prod", "group")
    )
    dialog.eks_version.setEditText("1.2.3")
    assert dialog.arguments[:3] == ["az", "k8s-extension", "update"]
    assert not hasattr(dialog, "chart")


def test_a_helm_release_asks_for_the_chart_the_repository_and_the_values(
    monkeypatch,
) -> None:
    present(monkeypatch)
    row = resource()
    dialog = PluginUpdateDialog(
        None, "prod", row, "1.0.0", "2.0.0", ["2.0.0", "1.0.0"], "https://r"
    )
    assert dialog.chart.text() == "web" and dialog.repository.text() == "https://r"
    assert dialog.arguments[:5] == ["helm", "--kube-context", "prod", "upgrade", "web"]
    dialog.values_file.setText("/v.yaml")
    dialog.reuse.setChecked(False)
    assert "--reset-values" in dialog.arguments and "/v.yaml" in dialog.arguments


def test_an_odd_input_shows_the_problem_and_cannot_be_run(monkeypatch) -> None:
    present(monkeypatch)
    dialog = PluginUpdateDialog(None, "prod", resource(), "1", "—", [])
    dialog.chart.setText("bad chart")
    assert dialog.arguments == [] and dialog.problem.text()
    assert not dialog.update_button.isEnabled()


def test_without_the_program_the_command_is_shown_but_cannot_be_run(
    monkeypatch,
) -> None:
    present(monkeypatch, missing=True)
    dialog = PluginUpdateDialog(None, "prod", resource(), "1", "—", ["2"])
    assert dialog.command.toPlainText().startswith("helm")
    assert dialog.arguments == [] and "not installed" in dialog.problem.text()
    assert not dialog.update_button.isEnabled()


def test_the_chart_of_a_release_is_the_one_it_installed_not_the_name_of_the_release(
    monkeypatch,
) -> None:
    present(monkeypatch)
    row = resource(name="external-secrets-op")

    named = PluginUpdateDialog(
        None, "prod", row, "1", "2", ["2"], "", None, ("", ""), "external-secrets"
    )
    unknown = PluginUpdateDialog(None, "prod", row, "1", "2", ["2"])

    assert named.chart.text() == "external-secrets"
    assert "external-secrets " in named.command.toPlainText() + " "
    assert unknown.chart.text() == "external-secrets-op"  # without it, the release
