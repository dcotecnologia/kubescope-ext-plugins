"""The latest version of what the Installed page lists.

An EKS add-on's latest version is the newest one EKS offers for the
cluster's Kubernetes version. A Helm release's is the version of the
chart of the same name at Artifact Hub, the one of an official or
verified publisher first: Helm does not keep where a chart came from, so
this is the best match, not a certainty. Nothing here raises: a version
that cannot be found is a dash. No Qt.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Protocol

from kubescope.sdk.errors import ClusterError

from kubescope.plugins import artifacthub

logger = logging.getLogger(__name__)

NONE = "—"
HELM_TTL = 600.0  # seconds a chart's latest version is kept
READERS = 8  # versions asked at the same time
CANDIDATES = 20  # charts of one name looked into for the installed version
_helm_cache: dict[str, tuple[float, str]] = {}


class Aws(Protocol):
    def run(
        self, context: str, command: list[str], region: str = ""
    ) -> dict[str, Any]: ...


def cluster_name(target: list[str]) -> str:
    """The name of the cluster in the arguments that name it."""
    return (
        target[target.index("--cluster-name") + 1] if "--cluster-name" in target else ""
    )


def eks_latest(aws: Aws, context: str, addon: str, cluster_version: str) -> str:
    """The newest version of an EKS add-on that the cluster's Kubernetes
    version can run, from `aws eks describe-addon-versions`."""
    try:
        document = aws.run(
            context, ["eks", "describe-addon-versions", "--addon-name", addon]
        )
    except ClusterError as error:
        logger.info("Latest version of %s not read: %s", addon, error)
        return NONE
    versions: list[dict[str, Any]] = [
        entry
        for item in document.get("addons") or []
        for entry in item.get("addonVersions") or []
    ]
    for entry in versions:  # the newest first
        version = entry.get("addonVersion")
        fits = any(
            isinstance(found, dict) and found.get("clusterVersion") == cluster_version
            for found in entry.get("compatibilities") or []
        )
        if isinstance(version, str) and (fits or not cluster_version):
            return version
    return NONE


def eks_versions(aws: Aws, context: str, addon: str) -> list[str]:
    """The versions EKS offers for an add-on, the newest first.

    Raises
    ClusterError.
    """
    document = aws.run(
        context, ["eks", "describe-addon-versions", "--addon-name", addon]
    )
    versions: list[str] = []
    for item in document.get("addons") or []:
        for entry in item.get("addonVersions") or []:
            version = entry.get("addonVersion")
            if isinstance(version, str) and version not in versions:
                versions.append(version)
    return versions


def _ranked(name: str) -> list[artifacthub.Chart]:
    """The charts of that name at Artifact Hub: an official publisher first,
    then a verified one, then a CNCF project, then the order of relevance."""
    found = artifacthub.search_charts(name, 0, 20).charts
    same = [c for c in found if c.name.casefold() == name.casefold() and c.version]
    return sorted(same, key=lambda c: (not c.official, not c.verified, not c.cncf))


def _bare(version: str) -> str:
    return version.strip().removeprefix("v")


def helm_match(name: str, installed: str = "") -> tuple[str, list[str]]:
    """Where a release's chart most likely comes from: the address of the
    repository and the versions it has, the newest first.

    Charts of one name are not one chart (many are called `prometheus`),
    so the first one that has the installed version among its own is
    taken; with none of them having it, the best publisher's. Raises
    CatalogError.
    """
    candidates = _ranked(name)[:CANDIDATES]
    first: tuple[str, list[str]] | None = None
    for chart in candidates:
        versions = artifacthub.package_versions(chart.repository, chart.name)
        found = (chart.repository_url, versions or [chart.version])
        first = first or found
        if installed and any(_bare(v) == _bare(installed) for v in versions):
            return found
    return first or ("", [])


def helm_latest(chart: str, installed: str = "") -> str:
    """The latest version of the chart of that name at Artifact Hub."""
    key = f"{chart}@{installed}"
    cached = _helm_cache.get(key)
    if cached and time.monotonic() - cached[0] < HELM_TTL:
        return cached[1]
    try:
        _url, versions = helm_match(chart, installed)
    except artifacthub.CatalogError as error:
        logger.info("Latest version of %s not read: %s", chart, error)
        return NONE
    latest = versions[0] if versions else NONE
    _helm_cache[key] = (time.monotonic(), latest)
    return latest


def update_available(installed: str, latest: str) -> bool:
    """Whether the latest version differs from the installed one."""
    if latest in ("", NONE):
        return False
    return bool(installed) and installed != NONE and _bare(installed) != _bare(latest)


def latest_versions(
    rows: list[Any],
    eks: Callable[[str], str],
    helm_chart: Callable[[Any], str],
) -> dict[tuple[str, str, str], str]:
    """The latest version of each row, by (kind, namespace, name), asked at
    the same time: `eks` for an add-on of EKS, `helm_chart` names the chart of
    a Helm release; an AKS extension or a GKE add-on does not say."""
    calls: dict[tuple[str, str, str], Callable[[], str]] = {}
    for row in rows:
        key = (row.kind, row.namespace, row.name)
        if row.kind == "Addon":
            calls[key] = partial(eks, row.name)
        elif row.kind == "HelmRelease":
            calls[key] = partial(helm_latest, helm_chart(row), row.values[1])
        else:
            calls[key] = lambda: NONE
    if not calls:
        return {}
    with ThreadPoolExecutor(max_workers=READERS) as pool:
        futures = {key: pool.submit(call) for key, call in calls.items()}
        return {key: future.result() for key, future in futures.items()}
