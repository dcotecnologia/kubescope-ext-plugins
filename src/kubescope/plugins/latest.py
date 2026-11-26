"""The latest version of what the Installed page lists.

An EKS add-on's latest version is the newest one EKS offers for the
cluster's Kubernetes version. A Helm release's is the version of the
chart of the same name at Artifact Hub, the one of an official or
verified publisher first: Helm does not keep where a chart came from, so
this is the best match, not a certainty. Nothing here raises: a version
that cannot be found is a dash. No Qt.
"""

import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Protocol

import yaml
from kubescope.sdk.errors import ClusterError

from kubescope.plugins import artifacthub

logger = logging.getLogger(__name__)

NONE = "—"
HELM_TTL = 600.0  # seconds a chart's latest version is kept
READERS = 8  # versions asked at the same time
CANDIDATES = 20  # charts of one name looked into for the installed version
INDEX_LIMIT = 30 * 1024 * 1024  # bytes of a repository's index that are read
INDEX_TIMEOUT = 20.0
_HTTPS = re.compile(r"https://[^\s]{1,300}")
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


def helm_match(
    name: str, installed: str = "", repository: str = ""
) -> tuple[str, list[str]]:
    """Where a release's chart most likely comes from: the address of the
    repository and the versions it has, the newest first.

    Charts of one name are not one chart (many are called `prometheus`),
    so the first one that has the installed version among its own is
    taken; with none of them having it, the best publisher's. Raises
    CatalogError.
    """
    if repository:  # the release says it, so there is nothing to guess
        return repository, repository_versions(repository, name)
    candidates = _ranked(name)[:CANDIDATES]
    first: tuple[str, list[str]] | None = None
    for chart in candidates:
        versions = artifacthub.package_versions(chart.repository, chart.name)
        found = (chart.repository_url, versions or [chart.version])
        first = first or found
        if installed and any(_bare(v) == _bare(installed) for v in versions):
            return found
    return first or ("", [])


def repository_versions(repository: str, chart: str) -> list[str]:
    """The versions a Helm repository has of a chart, the newest first, from
    the `index.yaml` of the repository.

    Raises
    CatalogError.
    """
    if not _HTTPS.fullmatch(repository):
        raise artifacthub.CatalogError("The repository must be an https address")
    request = urllib.request.Request(
        repository.rstrip("/") + "/index.yaml",
        headers={"User-Agent": "KubeScope-Plugins"},
    )
    try:
        with urllib.request.urlopen(request, timeout=INDEX_TIMEOUT) as response:
            raw = response.read(INDEX_LIMIT + 1)
        if len(raw) > INDEX_LIMIT:
            raise artifacthub.CatalogError("The index of the repository is too big")
        document = yaml.safe_load(raw)
    except (urllib.error.URLError, TimeoutError, OSError, yaml.YAMLError) as error:
        raise artifacthub.CatalogError(str(error).splitlines()[0]) from error
    entries = document.get("entries") if isinstance(document, dict) else None
    found = entries.get(chart) if isinstance(entries, dict) else None
    versions = [
        str(item["version"])
        for item in found or []
        if isinstance(item, dict) and item.get("version")
    ]
    return sorted(versions, key=_order, reverse=True)


def _order(version: str) -> tuple[tuple[int, ...], int, str]:
    """A sort key: the numbers first, a release before its pre-releases."""
    core, _, pre = _bare(version).partition("-")
    numbers = tuple(int(n) for n in re.findall(r"\d+", core)[:4])
    return numbers, 0 if pre else 1, pre


def helm_latest(chart: str, installed: str = "", repository: str = "") -> str:
    """The latest version of the chart of that name: in the repository the
    release says it came from, else at Artifact Hub."""
    key = f"{chart}@{installed}@{repository}"
    cached = _helm_cache.get(key)
    if cached and time.monotonic() - cached[0] < HELM_TTL:
        return cached[1]
    try:
        if repository:
            versions = repository_versions(repository, chart)
        else:
            _url, versions = helm_match(chart, installed)
    except artifacthub.CatalogError as error:
        logger.info("Latest version of %s not read: %s", chart, error)
        return NONE
    latest = versions[0] if versions else NONE
    if installed and not any(_bare(v) == _bare(installed) for v in versions):
        latest = NONE  # a chart of the same name, but not this one
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
    helm_repository: Callable[[Any], str] = lambda row: "",
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
            calls[key] = partial(
                helm_latest, helm_chart(row), row.values[1], helm_repository(row)
            )
        else:
            calls[key] = lambda: NONE
    if not calls:
        return {}
    with ThreadPoolExecutor(max_workers=READERS) as pool:
        futures = {key: pool.submit(call) for key, call in calls.items()}
        return {key: future.result() for key, future in futures.items()}
