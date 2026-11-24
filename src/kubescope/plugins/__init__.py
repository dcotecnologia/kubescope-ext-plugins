"""Plugins for KubeScope: the add-ons and Helm releases of the cluster with
their versions, and a catalog of Helm charts.

An extension.
"""

from kubescope.sdk import Context


def activate(ctx: Context) -> None:
    """What the app calls to run the extension."""
    from kubescope.plugins import extension

    extension.activate(ctx)
