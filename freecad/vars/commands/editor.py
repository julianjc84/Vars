# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

from __future__ import annotations
from freecad.vars.config import resources, commands
from freecad.vars.vendor.fcapi.lang import dtr
import FreeCAD as App  # type: ignore[import]


@commands.add(
    label=str(dtr("Vars", "Variables")),
    tooltip=str(dtr("Vars", "Edit Variables")),
    icon=resources.icon("vars.svg"),
    accel="Ctrl+Shift+K",
)
class EditVars:
    """
    Show the FreeCAD Vars Gui.
    """
    _editor_instance = None

    def on_activated(self) -> None:
        print("EditVars: on_activated called")
        from freecad.vars.ui.editors import VariablesEditor
        from PySide6.QtCore import QObject # or PySide.QtCore if not using PySide6

        cls = self.__class__ # Use self.__class__ to get the correct class

        if cls._editor_instance is not None and cls._editor_instance.dialog is not None:
            print("EditVars: Existing editor instance found, bringing to front.")
            # If an instance exists and its dialog is valid, bring it to front
            cls._editor_instance.dialog.raise_()
            cls._editor_instance.dialog.activateWindow()
            # Ensure the dialog is shown if it was hidden
            if not cls._editor_instance.dialog.isVisible():
                print("EditVars: Existing editor was hidden, showing now.")
                cls._editor_instance.dialog.show()
            return

        print("EditVars: No existing editor instance or dialog invalid, creating new one.")
        editor = VariablesEditor(App.activeDocument())
        cls._editor_instance = editor
        print(f"EditVars: New editor instance created: {editor}")

        # Ensure _editor_instance is reset when the dialog is closed
        # The dialog has WA_DeleteOnClose, so its destroyed signal is appropriate.
        def clear_instance():
            print(f"EditVars: clear_instance called for dialog of editor: {editor}")
            cls._editor_instance = None # Use the captured cls
            print("EditVars: _editor_instance set to None.")
            # Disconnect to avoid issues if somehow called again
            if editor.dialog: # Check if dialog still exists before disconnecting
                try:
                    editor.dialog.destroyed.disconnect(clear_instance)
                    print("EditVars: Disconnected clear_instance from dialog.destroyed.")
                except RuntimeError: # Already disconnected or object deleted
                    print("EditVars: clear_instance already disconnected or dialog deleted.")
                    pass

        if editor.dialog:
            print(f"EditVars: Connecting clear_instance to destroyed signal of dialog: {editor.dialog}")
            editor.dialog.destroyed.connect(clear_instance)
        else:
            print("EditVars: New editor has no dialog, cannot connect destroyed signal.")


    def is_active(self) -> bool:
        return bool(App.GuiUp and App.activeDocument())
