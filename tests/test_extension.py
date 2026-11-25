from kubescope.extensions import testing

from kubescope.plugins import activate, extension
from kubescope.plugins.extension import CatalogPage
from tests.conftest import FakeUi


def test_the_pages_go_into_the_monitoring_section_under_the_plugins_group(ctx) -> None:
    activate(ctx)
    assert [(p["section"], p["group"], p["title"]) for p in ctx.pages] == [
        ("Monitoring", "Plugins", "Catalog"),
        ("Monitoring", "Plugins", "Installed"),
    ]
    catalog, installed = ctx.pages
    assert installed["refresh"] is not None and "refresh" not in catalog
    first = installed["factory"]()
    assert installed["factory"]() is not first  # one of its own each time it is built


def test_the_catalog_is_searched_when_it_is_first_shown(ctx, monkeypatch) -> None:
    searched = []
    monkeypatch.setattr(
        extension.PluginsCatalog, "ensure", lambda self: searched.append(1)
    )
    CatalogPage(FakeUi()).shown()
    assert searched == [1]


def test_without_a_window_it_adds_nothing(ctx) -> None:
    ctx.ui = None
    activate(ctx)
    assert ctx.pages == []


def test_the_refresh_button_reads_the_page_that_is_in_the_window(
    ctx, monkeypatch
) -> None:
    activate(ctx)
    installed = ctx.pages[1]
    reloaded = []
    monkeypatch.setattr(
        extension.InstalledPage, "reload", lambda self: reloaded.append(self)
    )
    installed["refresh"]()  # no page yet
    widget = installed["factory"]()
    installed["refresh"]()
    assert len(reloaded) == 1
    widget.deleteLater()
    testing.settle()
    installed["refresh"]()  # a page that is gone is left alone
    assert len(reloaded) == 1


def test_a_page_that_goes_away_stops_listening(ctx) -> None:
    from kubescope.plugins.installed_page import InstalledPage

    stopped = []
    ctx.events.on = lambda event, handler: lambda: stopped.append(event)
    page = InstalledPage(ctx)
    page.widget.deleteLater()
    testing.settle()
    assert sorted(stopped) == ["context_changed", "theme_changed", "write_mode_changed"]
