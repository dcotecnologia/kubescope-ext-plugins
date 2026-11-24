"""What the app calls to run the Plugins: two pages of the side menu, Installed
and Catalog."""

from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from kubescope.plugins.catalog import CatalogWidgets, PluginsCatalog
from kubescope.plugins.installed_page import InstalledPage

# the section of the app that already holds Workloads and Configuration: the
# name is the English one of the app, whatever the language, so it is not
# translated; the group is the one the Plugins always had
SECTION = "Monitoring"
GROUP = "Plugins"


class CatalogPage(QWidget):
    """The catalog, built when it is first shown."""

    def __init__(self) -> None:
        super().__init__()
        self.widgets = CatalogWidgets(self)
        self.catalog = PluginsCatalog(self.widgets, self)

    def shown(self) -> None:
        self.catalog.ensure()


def activate(ctx: Any) -> None:
    if ctx.ui is None:  # the terminal has no pages
        return
    translate = QCoreApplication.translate
    current: list[InstalledPage] = []  # the page that is in the window now

    def make_installed() -> InstalledPage:
        """A page of its own each time: the app deletes the one it had when it
        builds its menu again, so one kept here would be gone."""
        page = InstalledPage(ctx)
        current[:] = [page]
        return page

    def refresh_installed() -> None:
        if current and isValid(current[0]):
            current[0].reload()

    ctx.add_page(
        SECTION,
        translate("PluginsExtension", GROUP),
        translate("PluginsExtension", "Catalog"),
        CatalogPage,
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
