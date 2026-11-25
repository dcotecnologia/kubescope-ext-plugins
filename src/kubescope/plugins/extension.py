"""What the app calls to run the Plugins: two pages of the side menu, Installed
and Catalog."""

from typing import Any

from kubescope.sdk import translate

from kubescope.plugins.catalog import CatalogWidgets, PluginsCatalog
from kubescope.plugins.installed_page import InstalledPage

# the section of the app that already holds Workloads and Configuration: the
# name is the English one of the app, whatever the language, so it is not
# translated; the group is the one the Plugins always had
SECTION = "Monitoring"
GROUP = "Plugins"


class CatalogPage:
    """The catalog, built when it is first shown."""

    def __init__(self, ui: Any) -> None:
        self.widget = ui.components.widget(shown=self.shown)
        self.widgets = CatalogWidgets(self.widget, ui.components)
        self.catalog = PluginsCatalog(self.widgets, self.widget, ui.run_action)

    def shown(self) -> None:
        self.catalog.ensure()


def activate(ctx: Any) -> None:
    if ctx.ui is None:  # the terminal has no pages
        return
    current: list[InstalledPage] = []  # the page that is in the window now

    def make_installed() -> Any:
        """A page of its own each time: the app deletes the one it had when it
        builds its menu again, so one kept here would be gone."""
        page = InstalledPage(ctx)
        current[:] = [page]
        return page.widget

    def refresh_installed() -> None:
        if current and ctx.ui.components.is_alive(current[0].widget):
            current[0].reload()

    ctx.add_page(
        SECTION,
        translate("PluginsExtension", GROUP),
        translate("PluginsExtension", "Catalog"),
        lambda: CatalogPage(ctx.ui).widget,
        subtitle=translate("PluginsExtension", "Helm charts of Artifact Hub"),
    )
    ctx.add_page(
        SECTION,
        translate("PluginsExtension", GROUP),
        translate("PluginsExtension", "Installed"),
        make_installed,
        subtitle=translate(
            "PluginsExtension", "Add-ons and Helm releases of the cluster"
        ),
        refresh=refresh_installed,
    )
