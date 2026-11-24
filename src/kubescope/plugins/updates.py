"""The commands that update what the Installed page lists, built from what the
person types.

An Amazon EKS add-on is updated with `aws eks update-addon`, an AKS
extension with `az k8s-extension update`, a Helm release with `helm
upgrade`. Nothing here runs a command: the app runs it, only in the
write mode, after the person confirmed the dialog. No Qt.
"""

import re
import shlex

from kubescope.sdk.errors import ClusterError
from kubescope.sdk.flatpak import in_flatpak
from kubescope.sdk.programs import find_program

CONFLICTS = ("NONE", "OVERWRITE", "PRESERVE")  # what EKS does with changed fields
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}")
_CLUSTER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_REPO = re.compile(r"https://[^\s]{1,300}")
_PATH = re.compile(r"[^\s\0-\x1f]{1,500}")


def eks_update_arguments(
    target: list[str], addon: str, version: str, conflicts: str = "NONE"
) -> list[str]:
    """The AWS CLI command that moves an add-on of an EKS cluster, named by
    `target` (the arguments the app gives for the context), to a version."""
    if not _NAME.fullmatch(addon):
        raise ClusterError("That is not the name of an add-on")
    if not _VERSION.fullmatch(version):
        raise ClusterError("Give the version to update to")
    if conflicts not in CONFLICTS:
        raise ClusterError("Choose what to do with the fields that differ")
    return [
        "aws",
        "eks",
        "update-addon",
        *target,
        "--addon-name",
        addon,
        "--addon-version",
        version,
        "--resolve-conflicts",
        conflicts,
        "--output",
        "json",
    ]


def aks_update_arguments(
    cluster_name: str, group: str, extension: str, version: str
) -> list[str]:
    """The `az k8s-extension update` command that moves an extension to a
    version; a version that is asked for turns the automatic minor upgrades
    off, as the command requires."""
    if not _CLUSTER.fullmatch(extension):
        raise ClusterError("That is not the name of an extension")
    if not _VERSION.fullmatch(version):
        raise ClusterError("Give the version to update to")
    if not _CLUSTER.fullmatch(cluster_name) or not _CLUSTER.fullmatch(group):
        raise ClusterError("That is not the name of a cluster")
    return [
        "az",
        "k8s-extension",
        "update",
        "--name",
        extension,
        "--cluster-name",
        cluster_name,
        "--resource-group",
        group,
        "--cluster-type",
        "managedClusters",
        "--version",
        version,
        "--auto-upgrade-minor-version",
        "false",
        "--yes",
        "--output",
        "json",
    ]


def helm_upgrade_arguments(
    context: str,
    namespace: str,
    release: str,
    chart: str,
    version: str = "",
    repository: str = "",
    reuse_values: bool = True,
    values_file: str = "",
) -> list[str]:
    """The `helm upgrade` command for a release.

    `chart` is a reference as Helm takes it (`repo/name`, `oci://...`, a
    path), or the bare name of a chart when `repository` gives the
    address to read it from. By default the values the release already
    has are kept.
    """
    if not _NAME.fullmatch(release) or not _NAME.fullmatch(namespace):
        raise ClusterError("That is not the name of a release")
    if not _NAME.fullmatch(chart):
        raise ClusterError("Give the chart to upgrade the release with")
    if version and not _VERSION.fullmatch(version):
        raise ClusterError("That is not a chart version")
    if repository and not _REPO.fullmatch(repository):
        raise ClusterError("The repository must be an https address")
    if values_file and not _PATH.fullmatch(values_file):
        raise ClusterError("That is not the path of a values file")
    return [
        "helm",
        "--kube-context",
        context,
        "upgrade",
        release,
        chart,
        "--namespace",
        namespace,
        *(["--repo", repository] if repository else []),
        *(["--version", version] if version else []),
        "--reuse-values" if reuse_values else "--reset-values",
        *(["--values", values_file] if values_file else []),
        "--wait",
        "--timeout",
        "5m",
    ]


def program_missing(program: str) -> bool:
    """Whether the program that runs an update is not installed.

    In a Flatpak the programs are the host's, which the sandbox cannot
    look at, so it is taken as there.
    """
    return not in_flatpak() and find_program(program) is None


def commands(arguments: list[str]) -> str:
    """The command as the person would type it, to show before it runs."""
    return shlex.join(arguments)
