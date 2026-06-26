# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations
from freecad.vars.config import resources, commands
from freecad.vars.vendor.fcapi.lang import dtr
import FreeCADGui as Gui  # type: ignore[import]


@commands.add(
    label=str(dtr("Vars", "Preferences")),
    tooltip=str(dtr("Vars", "Open Preferences")),
    icon=resources.icon("preferences-settings.svg"),
)
class OpenPreferences:
    """
    Open the FreeCAD Preferences dialog.
    """

    def on_activated(self) -> None:
        Gui.runCommand('Std_DlgPreferences', 0)

    def is_active(self) -> bool:
        return True
