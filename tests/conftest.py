"""Fixtures of the tests of the Plugins."""

import pytest

# the tests run her in the app, so they take its real components
from kubescope.extensions import testing
from kubescope.extensions.components import UiComponents


@pytest.fixture(autouse=True)
def delete_the_windows():
    """Delete what a test shows before the application goes away: a window that
    outlives it crashes the run when it ends."""
    yield from testing.cleanup()


class FakeUi:
    """`ctx.ui`: runs an action at once and remembers what was shown."""

    def __init__(self) -> None:
        self.window = UiComponents().widget()
        self.components = UiComponents(lambda status: (status, "fill"))
        self.messages: list[tuple] = []
        self.documents: list[tuple] = []
        self.notices: list[tuple] = []  # of the system
        self.can_notify = True
        self.quiet: list[bool] = []  # of each action, in order

    def themed(self, color, text=False):
        return color

    def style_box(self, box) -> None:
        pass

    def show_message(self, icon, title, text) -> None:
        self.messages.append((icon, title, text))

    def show_system_notification(
        self, title, message, on_click=None, category=""
    ) -> bool:
        if self.can_notify:
            self.notices.append((title, message))
        return self.can_notify

    def show_json(self, title, document) -> None:
        self.documents.append((title, document))

    def run_action(self, function, on_success, *arguments, on_error=None, quiet=False):
        self.quiet.append(quiet)
        try:
            answer = function(*arguments)
        except Exception as error:
            if on_error is None:
                raise
            on_error(str(error))
            return
        on_success(answer)


class FakeCluster:
    def __init__(self) -> None:
        self.rows: list = []
        self.failure: Exception | None = None
        self.asked: list[tuple] = []
        self.charts: dict[str, str] = {}  # the chart of a release, by its name

    def get_resources(self, context, namespace, kind):
        self.asked.append((context, namespace, kind))
        if self.failure is not None:
            raise self.failure
        return [], list(self.rows)

    def get_resource_details(self, context, kind, namespace, name):
        self.asked.append(("details", context, kind, namespace, name))
        if self.failure is not None:
            raise self.failure
        return {"kind": kind, "name": name}

    def helm_chart_name(self, context, namespace, release):
        return self.charts.get(release, release)

    def eks_target(self, context):
        return ["--cluster-name", "prod", "--region", "sa-east-1"]

    def aks_cluster(self, context):
        return ("aks-prod", "group")


class FakeAws:
    def __init__(self) -> None:
        self.answers: dict[str, dict] = {}  # by the verb
        self.failure: Exception | None = None
        self.commands: list[list[str]] = []

    def run(self, context, command, region=""):
        self.commands.append(command)
        if self.failure is not None:
            raise self.failure
        return self.answers.get(command[1], {})


class FakeWrites:
    def __init__(self) -> None:
        self.updates: list[tuple] = []
        self.removals: list[tuple] = []
        self.failure: Exception | None = None
        self.removal_failures: dict[str, Exception] = {}  # by the name in the command

    def run_remove(self, context, arguments):
        for name, error in self.removal_failures.items():
            if name in arguments:
                raise error
        self.removals.append((context, arguments))
        return "ok"

    def run_update(self, context, arguments):
        if self.failure is not None:
            raise self.failure
        self.updates.append((context, arguments))
        return "ok"


class FakeEvents:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)
        return lambda: None

    def fire(self, event, **arguments):
        for handler in self.handlers.get(event, []):
            handler(**arguments)


class FakeApp:
    write_mode = True


class FakeCtx:
    """What the app gives the extension, in the hands of the test."""

    id = "kubescope.plugins"

    def __init__(self) -> None:
        self.ui: FakeUi | None = FakeUi()
        self.cluster = FakeCluster()
        self.aws = FakeAws()
        self.writes = FakeWrites()
        self.events = FakeEvents()
        self.app = FakeApp()
        self.current_context: str | None = "prod"
        self.pages: list[dict] = []
        self.page_sets: list[tuple[str, list]] = []
        self.cleanups: list = []

    def add_page(self, section, group, title, factory, **options):
        self.pages.append(
            {"section": section, "group": group, "title": title, "factory": factory}
            | options
        )

    def set_pages(self, key, pages) -> None:
        self.page_sets.append((key, list(pages)))

    def on_unload(self, callback) -> None:
        self.cleanups.append(callback)


@pytest.fixture
def ctx():
    return FakeCtx()


def resource(kind="HelmRelease", name="web", namespace="ops", values=None, age="1d"):
    """A row of the add-ons list as the app gives it: status, chart, app,
    source, last update."""
    from kubescope.sdk.models import ClusterResource

    source = "Helm" if kind == "HelmRelease" else "EKS"
    return ClusterResource(
        namespace,
        kind,
        name,
        values or ("deployed", "1.0.0", "v9", source, "2d"),
        age,
    )
