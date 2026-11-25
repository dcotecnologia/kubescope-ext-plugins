import pytest
from kubescope.sdk.errors import ClusterError

from kubescope.plugins import artifacthub, latest
from tests.conftest import FakeAws, resource

DOCUMENT = {
    "addons": [
        {
            "addonVersions": [
                {"addonVersion": "v3", "compatibilities": [{"clusterVersion": "1.35"}]},
                {"addonVersion": "v2", "compatibilities": [{"clusterVersion": "1.34"}]},
                {"addonVersion": "v2", "compatibilities": ["odd"]},
                {"addonVersion": 5},
            ]
        }
    ]
}


def test_the_latest_of_an_eks_addon_is_the_newest_the_cluster_can_run() -> None:
    aws = FakeAws()
    aws.answers["describe-addon-versions"] = DOCUMENT
    assert latest.eks_latest(aws, "ctx", "vpc-cni", "1.34") == "v2"
    assert latest.eks_latest(aws, "ctx", "vpc-cni", "1.35") == "v3"
    assert latest.eks_latest(aws, "ctx", "vpc-cni", "1.20") == "—"
    assert latest.eks_latest(aws, "ctx", "vpc-cni", "") == "v3"
    assert aws.commands[0] == [
        "eks",
        "describe-addon-versions",
        "--addon-name",
        "vpc-cni",
    ]


def test_a_failure_leaves_a_dash_and_the_versions_listed_raise() -> None:
    aws = FakeAws()
    aws.failure = ClusterError("denied")
    assert latest.eks_latest(aws, "ctx", "vpc-cni", "1.34") == "—"
    with pytest.raises(ClusterError):
        latest.eks_versions(aws, "ctx", "vpc-cni")


def test_the_versions_are_those_eks_lists_without_repeats() -> None:
    aws = FakeAws()
    aws.answers["describe-addon-versions"] = DOCUMENT
    assert latest.eks_versions(aws, "ctx", "vpc-cni") == ["v3", "v2"]


def test_the_cluster_is_named_by_its_arguments() -> None:
    assert latest.cluster_name(["--cluster-name", "prod", "--region", "r"]) == "prod"
    assert latest.cluster_name(["--region", "r"]) == ""


def _chart(name, version, **marks):
    return artifacthub.Chart(
        name,
        "repo",
        version,
        "",
        "",
        marks.get("official", False),
        marks.get("verified", False),
        marks.get("cncf", False),
        "https://r",
    )


def test_a_chart_is_matched_by_the_installed_version(monkeypatch) -> None:
    latest._helm_cache.clear()
    monkeypatch.setattr(
        artifacthub,
        "search_charts",
        lambda *_a: artifacthub.Results(
            [_chart("grafana", "1.4.8"), _chart("other", "9"), _chart("grafana", "")], 3
        ),
    )
    monkeypatch.setattr(
        artifacthub, "package_versions", lambda repo, name: ["1.4.8", "1.4.7", "v3.6.2"]
    )
    assert latest.helm_match("grafana", "3.6.2")[1][0] == "1.4.8"
    assert latest.helm_latest("grafana", "v3.6.2") == "1.4.8"
    assert latest.helm_latest("grafana", "v3.6.2") == "1.4.8"  # kept
    assert latest.helm_match("grafana", "0.0.1")[1] == ["1.4.8", "1.4.7", "v3.6.2"]


def test_a_chart_that_cannot_be_found_is_a_dash(monkeypatch) -> None:
    latest._helm_cache.clear()
    monkeypatch.setattr(
        artifacthub, "search_charts", lambda *_a: artifacthub.Results([], 0)
    )
    assert latest.helm_match("g") == ("", [])
    assert latest.helm_latest("g") == "—"

    def refuse(*_a):
        raise artifacthub.CatalogError("offline")

    monkeypatch.setattr(artifacthub, "search_charts", refuse)
    assert latest.helm_latest("x") == "—"


def test_a_chart_without_versions_falls_back_to_its_own(monkeypatch) -> None:
    monkeypatch.setattr(
        artifacthub,
        "search_charts",
        lambda *_a: artifacthub.Results([_chart("g", "5")], 1),
    )
    monkeypatch.setattr(artifacthub, "package_versions", lambda *_a: [])
    assert latest.helm_match("g") == ("https://r", ["5"])


@pytest.mark.parametrize(
    ("installed", "newest", "expected"),
    [
        ("v1", "v2", True),
        ("v2", "v2", False),
        ("v2", "—", False),
        ("—", "v2", False),
        ("v1.3.0", "1.3.0", False),
    ],
)
def test_an_update_is_available_when_the_latest_differs(
    installed, newest, expected
) -> None:
    assert latest.update_available(installed, newest) is expected


def test_each_row_is_asked_by_its_kind(monkeypatch) -> None:
    monkeypatch.setattr(
        latest, "helm_latest", lambda chart, installed: f"helm-{chart}-{installed}"
    )
    rows = [
        resource("Addon", "vpc-cni", ""),
        resource("HelmRelease", "web"),
        resource("AksExtension", "flux", ""),
    ]
    found = latest.latest_versions(rows, lambda name: f"eks-{name}", lambda row: "site")
    assert found == {
        ("Addon", "", "vpc-cni"): "eks-vpc-cni",
        ("HelmRelease", "ops", "web"): "helm-site-1.0.0",
        ("AksExtension", "", "flux"): "—",
    }
    assert latest.latest_versions([], lambda n: "", lambda r: "") == {}


def test_a_chart_far_down_the_ranking_is_found_by_the_installed_version(
    monkeypatch,
) -> None:
    charts = [_chart("loki", "21.6.0", verified=True)]
    charts += [_chart("loki", str(n)) for n in range(1, 10)]
    charts.append(_chart("loki", "7.7.0"))
    monkeypatch.setattr(
        artifacthub, "search_charts", lambda *_a: artifacthub.Results(charts, 11)
    )
    asked: list[int] = []

    def versions(*_a):
        asked.append(1)
        return ["7.7.0", "7.5.0"] if len(asked) == 11 else ["21.6.0"]

    monkeypatch.setattr(artifacthub, "package_versions", versions)
    assert latest.helm_match("loki", "7.5.0")[1][0] == "7.7.0"
