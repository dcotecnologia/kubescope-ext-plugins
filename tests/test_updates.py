import pytest
from kubescope.sdk.errors import ClusterError

from kubescope.plugins import updates

TARGET = ["--cluster-name", "prod", "--region", "sa-east-1"]


def test_the_eks_update_names_the_addon_version_and_conflict_rule() -> None:
    arguments = updates.eks_update_arguments(
        TARGET, "vpc-cni", "v1.2.3-eksbuild.1", "OVERWRITE"
    )
    assert arguments[:3] == ["aws", "eks", "update-addon"]
    assert arguments[arguments.index("--addon-name") + 1] == "vpc-cni"
    assert arguments[arguments.index("--resolve-conflicts") + 1] == "OVERWRITE"
    assert "--cluster-name" in arguments


@pytest.mark.parametrize(
    ("addon", "version", "conflicts"),
    [("bad name", "v1", "NONE"), ("vpc-cni", "", "NONE"), ("vpc-cni", "v1", "X")],
)
def test_the_eks_update_refuses_what_is_not_a_name_a_version_or_a_rule(
    addon, version, conflicts
) -> None:
    with pytest.raises(ClusterError):
        updates.eks_update_arguments(TARGET, addon, version, conflicts)


def test_the_aks_update_turns_the_automatic_upgrades_off() -> None:
    arguments = updates.aks_update_arguments("aks", "group", "flux", "1.2.3")
    assert arguments[:3] == ["az", "k8s-extension", "update"]
    assert arguments[arguments.index("--auto-upgrade-minor-version") + 1] == "false"
    assert arguments[arguments.index("--resource-group") + 1] == "group"


@pytest.mark.parametrize(
    ("cluster", "group", "extension", "version"),
    [
        ("aks", "group", "bad name", "1"),
        ("aks", "group", "flux", ""),
        ("bad name", "group", "flux", "1"),
        ("aks", "bad group", "flux", "1"),
    ],
)
def test_the_aks_update_refuses_odd_inputs(cluster, group, extension, version) -> None:
    with pytest.raises(ClusterError):
        updates.aks_update_arguments(cluster, group, extension, version)


def test_the_helm_upgrade_keeps_the_values_and_reads_the_repository() -> None:
    arguments = updates.helm_upgrade_arguments(
        "ctx", "ops", "web", "web", "1.2.3", "https://charts.example.com"
    )
    assert arguments[:5] == ["helm", "--kube-context", "ctx", "upgrade", "web"]
    assert "--reuse-values" in arguments
    assert arguments[arguments.index("--repo") + 1] == "https://charts.example.com"
    reset = updates.helm_upgrade_arguments(
        "ctx", "ops", "web", "repo/web", reuse_values=False, values_file="/v.yaml"
    )
    assert (
        "--reset-values" in reset and "--values" in reset and "--version" not in reset
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"release": "bad name"},
        {"chart": "bad chart"},
        {"version": "bad version"},
        {"repository": "http://x"},
        {"values_file": "a b"},
    ],
)
def test_the_helm_upgrade_refuses_odd_inputs(bad) -> None:
    arguments = {
        "context": "ctx",
        "namespace": "ops",
        "release": "web",
        "chart": "web",
    } | bad
    with pytest.raises(ClusterError):
        updates.helm_upgrade_arguments(**arguments)


def test_a_program_is_missing_when_it_is_not_found_outside_a_flatpak(
    monkeypatch,
) -> None:
    monkeypatch.setattr(updates, "in_flatpak", lambda: False)
    monkeypatch.setattr(updates, "find_program", lambda _p: None)
    assert updates.program_missing("helm") is True
    monkeypatch.setattr(updates, "find_program", lambda _p: "/usr/bin/helm")
    assert updates.program_missing("helm") is False
    monkeypatch.setattr(updates, "in_flatpak", lambda: True)
    monkeypatch.setattr(updates, "find_program", lambda _p: None)
    assert updates.program_missing("helm") is False  # the host's, unseen


def test_the_command_is_shown_as_the_person_would_type_it() -> None:
    assert updates.commands(["helm", "upgrade", "a b"]) == "helm upgrade 'a b'"
