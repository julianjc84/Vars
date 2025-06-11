# SPDX-License: LGPL-3.0-or-later
# (c) 2025 Frank David Martínez Muñoz. <mnesarco at gmail.com>

"""
FreeCAD Vars: Variables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeAlias
import operator as op

from freecad.vars.utils import get_unique_name
from freecad.vars.vendor.fcapi.fpo import PropertyMode
from freecad.vars.config import preferences

import FreeCAD as App  # type: ignore
from collections.abc import Callable
import contextlib

if TYPE_CHECKING:
    from FreeCAD import Document, DocumentObject  # type: ignore


VarOptions: TypeAlias = list[str] | Callable[[], list[str]] | None


def get_vars_group(doc: Document | None = None) -> DocumentObject:
    """
    Return the document object group where all variables are stored.

    :param doc: The document to search in. Defaults to the active document.
    :return: The group where variables are stored.
    """
    doc = doc or App.activeDocument()
    group: DocumentObject = doc.getObject("XVarGroup")
    if not group:
        group = doc.addObject("App::DocumentObjectGroup", "XVarGroup")
        group.Label = "Variables"
    return group


def _get_or_assign_initial_group_sort_key(group_name: str, doc: Document | None) -> int:
    print(f"DEV: _get_or_assign_initial_group_sort_key for group: {group_name}")
    _doc = doc or App.ActiveDocument
    if not _doc:
        print("DEV: ERROR - No document in _get_or_assign_initial_group_sort_key")
        return -1  # Should not happen if called correctly

    all_gsk_values = []
    processed_groups_keys: dict[str, int] = {}

    for var_obj in get_vars(_doc):  # Using existing get_vars
        if hasattr(var_obj.varset, "GroupSortKey"):
            gsk = var_obj.varset.GroupSortKey
            if var_obj.group not in processed_groups_keys:
                processed_groups_keys[var_obj.group] = gsk
            # Ensure consistency if multiple vars in same group have different GSK (should not happen)
            elif processed_groups_keys[var_obj.group] != gsk:
                print(
                    f"DEV: WARNING - Inconsistent GroupSortKey for group {var_obj.group}. Using first encountered: {processed_groups_keys[var_obj.group]}"
                )

    if group_name in processed_groups_keys:
        print(
            f"DEV: Found existing GroupSortKey for {group_name}: {processed_groups_keys[group_name]}"
        )
        return processed_groups_keys[group_name]

    # New group, assign new key
    current_max_gsk = -1
    if processed_groups_keys:
        current_max_gsk = max(processed_groups_keys.values())

    new_gsk = current_max_gsk + 1
    print(f"DEV: Assigning new GroupSortKey for {group_name}: {new_gsk}")
    return new_gsk


def create_var(
    *,
    name: str,
    var_type: str,
    value: Any | None = None,
    options: VarOptions = None,
    description: str = "",
    expression: str | None = None,
    group: str = "Default",
    doc: Document | None = None,
) -> bool:
    print(f"DEV: create_var called for: {name}, group: {group}")
    # Ensure doc is resolved
    _doc = doc or App.ActiveDocument
    if not _doc:
        print("DEV: ERROR - No document in create_var")
        return False

    name = sanitize_var_name(name)
    doc = doc or App.activeDocument()

    if existing_var_name(name, doc):
        return False

    if var_type == "App::PropertyEnumeration":
        if options is None:
            msg = "options must be provided if var_type is App::PropertyEnumeration"
            raise ValueError(msg)
    elif options is not None:
        msg = "options must be None if var_type is not App::PropertyEnumeration"
        raise ValueError(msg)

    varset: DocumentObject = doc.addObject("App::VarSet", get_unique_name(doc))
    varset.Label = name

    if hasattr(varset, "Label2"):
        varset.Label2 = description

    if callable(options):
        options = options()

    varset.addProperty(var_type, "Value", "", description, enum_vals=options)

    varset.addProperty(
        "App::PropertyString",
        "Description",
        "",
        "Variable Description",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.Description = description or ""

    varset.addProperty(
        "App::PropertyString",
        "VarGroup",
        "",
        "Variable Group",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.VarGroup = (group or "Default").title()

    varset.addProperty(
        "App::PropertyInteger",
        "SortKey",
        "",
        "Variable Sort Key",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.SortKey = 0

    varset.addProperty(
        "App::PropertyBool",
        "Hidden",
        "",
        "Hide variable from UI",
        PropertyMode.Output | PropertyMode.NoRecompute,
    )
    varset.Hidden = False

    if expression:
        varset.setExpression("Value", expression, "Calculated")
        varset.recompute()
    elif value is not None:
        varset.Value = value

    if preferences.hide_varsets():
        varset.ViewObject.ShowInTree = False

    # At the point of adding properties to varset:
    if not hasattr(varset, "GroupSortKey"):
        print(f"DEV: Adding GroupSortKey property to varset for {name}")
        varset.addProperty(
            "App::PropertyInteger",
            "GroupSortKey",
            "",
            "Group Sort Key",
            PropertyMode.Output | PropertyMode.NoRecompute,
        )
        initial_gsk = _get_or_assign_initial_group_sort_key(group, _doc)
        varset.GroupSortKey = initial_gsk
        print(f"DEV: Set initial GroupSortKey for {name} (group {group}) to: {initial_gsk}")
    elif varset.GroupSortKey is None:  # Or some other check if it might exist but be uninitialized
        # This case might occur if property was added but not set, or old file.
        initial_gsk = _get_or_assign_initial_group_sort_key(group, _doc)
        varset.GroupSortKey = initial_gsk
        print(f"DEV: Varset {name} had GroupSortKey property but no value. Set to: {initial_gsk}")
    else:
        # If var is being moved to a new group, its GSK might need update here or elsewhere
        print(f"DEV: Varset {name} already has GroupSortKey: {varset.GroupSortKey}. Group: {group}")
        # If the variable's group is changing, we might need to update its GSK
        # This logic might be better handled when a variable's group property is changed.
        # For now, assume create_var is for new vars or vars where group is already correct.

    get_vars_group(doc).addObject(varset)

    return True


def rename_var(
    name: str,
    new_name: str,
    description: str | None = None,
    doc: Document | None = None,
) -> bool:
    """
    Rename a variable.

    :param name: The label name of the variable to rename.
    :param new_name: The new label name of the variable.
    :param description: The new description of the variable, if any.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was renamed, False otherwise. raise error if var does not exists.
    """
    return Variable(doc or App.activeDocument(), name).rename(new_name, description)


def delete_var(name: str, doc: Document | None = None) -> bool:
    """
    Delete a variable.

    :param name: The label name of the variable to delete.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and deleted, False otherwise.
    """
    return Variable(doc or App.activeDocument(), name).delete()


def get_var(name: str, doc: Document | None = None) -> Any:
    """
    Retrieve the value of a variable by its label name.

    This function searches through the document for objects with the specified
    label name and checks if they have a 'Value' attribute and their name
    starts with 'Var'. If such an object is found, its value is returned.

    :param name: The label name of the variable.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The value of the variable or raise error if not found.
    """
    return Variable(doc or App.activeDocument(), name).value


def get_varset(name: str, doc: Document | None = None) -> DocumentObject | None:
    """
    Retrieve the variable set (VarSet) object by its label name.

    This function searches through the document for objects with the specified
    label name and checks if they have a 'Value' attribute and their name
    starts with 'Var'. If such an object is found, it is returned.

    :param name: The label name of the variable set to search for.
    :param doc: The document in which to search for the variable set. Defaults
                to the active document if not provided.
    :return: The matching DocumentObject if found, otherwise None.
    """
    doc = doc or App.activeDocument()
    objects: list[DocumentObject] = doc.getObjectsByLabel(name)
    for obj in objects:
        if hasattr(obj, "Value") and obj.Name.startswith("XVar_"):
            return obj
    return None


def set_var(name: str, value: Any, doc: Document | None = None) -> None:
    """
    Set the value of an existing variable.

    :param name: The name of the variable to set.
    :param value: The new value to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).value = value


def set_var_description(name: str, description: str, doc: Document | None = None) -> None:
    """
    Set the description of an existing variable.

    :param name: The name of the variable to modify.
    :param description: The new description to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).description = description


def set_var_options(name: str, options: VarOptions, doc: Document | None = None) -> None:
    """
    Set the options of an existing variable.

    :param name: The name of the variable to modify.
    :param options: The new options to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).options = options


def get_var_options(name: str, doc: Document | None = None) -> list[str]:
    """
    Retrieve the options of an existing variable.

    :param name: The name of the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: The options of the variable as a list of strings if found, raise otherwise.
    """
    return Variable(doc or App.activeDocument(), name).options


def set_var_expression(name: str, expression: str | None, doc: Document | None = None) -> None:
    """
    Set the expression of an existing variable.

    :param name: The name of the variable to modify.
    :param expression: The new expression to assign to the variable.
                       If None, the expression is cleared.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).expression = expression


def get_var_expression(name: str, doc: Document | None = None) -> str | None:
    """
    Retrieve the expression associated with a variable.

    This function searches for the expression linked to the specified variable
    within the document's expression engine. If the variable has an expression
    associated with it, the expression is returned.

    :param name: The label name of the variable.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The expression as a string if found, otherwise None.
    """
    return Variable(doc or App.activeDocument(), name).expression


def set_var_group(name: str, group: str, doc: Document | None = None) -> None:
    """
    Set the group of an existing variable.

    :param name: The name of the variable to modify.
    :param group: The new group to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    """
    Variable(doc or App.activeDocument(), name).group = group


def get_var_group(name: str, doc: Document | None = None) -> str:
    """
    Get the group of an existing variable.

    :param name: The name of the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: The group of the variable.
    """
    return Variable(doc or App.activeDocument(), name).group


def sanitize_var_name(name: str) -> str:
    """
    Check if a name is a valid variable name.

    :param name: The name to check.
    :raises ValueError: If the name is invalid.
    """
    name = (name or "").strip()
    if not name or not name.isidentifier():
        msg = f"Invalid var name: '{name}'"
        raise ValueError(msg)
    return name


def is_var(obj: DocumentObject | None) -> bool:
    """
    Check if an object is a variable.

    :param obj: The object to check.
    :return: True if the object is a variable, False otherwise.
    """
    return obj and obj.TypeId == "App::VarSet" and obj.Name.startswith("XVar_")


def get_vars(doc: Document | None = None) -> list[Variable]:
    """
    Retrieve all variable names in a document.

    :param doc: The document where to search for variables. Defaults to ActiveDocument.
    :return: A list of variable names.
    """
    doc = doc or App.activeDocument()
    return [Variable(doc, obj.Label) for obj in doc.findObjects("App::VarSet") if is_var(obj)]


def get_groups(doc: Document | None = None) -> list[str]:
    """
    Retrieve all variable groups in a document.

    :param doc: The document where to search for variables. Defaults to ActiveDocument.
    :return: A list of variable groups.
    """
    doc = doc or App.activeDocument()
    existing_groups = {obj.VarGroup for obj in doc.findObjects("App::VarSet") if is_var(obj)}
    existing_groups.add("Default")
    return sorted(existing_groups)


def set_var_type(
    name: str,
    new_type: str,
    doc: Document | None = None,
    converter: Callable | None = None,
) -> bool:
    """
    Set the type of an existing variable.

    :param name: The name of the variable to modify.
    :param var_type: The new type to assign to the variable.
    :param doc: The document where the variable exists. Defaults to the active document.
    :return: True if the variable was found and set, False otherwise.
    """
    doc = doc or App.activeDocument()
    if varset := get_varset(name, doc):
        if new_type not in varset.supportedProperties():
            msg = f"Invalid var type: '{new_type}'"
            raise ValueError(msg)

        old_type = varset.getTypeIdOfProperty("Value")
        if old_type == new_type:
            return False

        # Custom converter
        if converter:
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if value:
                with contextlib.suppress(Exception):
                    varset.Value = converter(value)
            return True

        # List to base (use first value if any)
        if old_type == f"{new_type}List":
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if isinstance(value, list) and value:
                varset.Value = value[0]
            return True

        # Base to list
        if new_type == f"{old_type}List":
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if value:
                varset.Value = [value]
            return True

        # Enumeration to base (TODO)

        # List to list
        if old_type.endswith("List") and new_type.endswith("List"):
            value = varset.Value
            varset.removeProperty("Value")
            varset.addProperty(new_type, "Value", "", varset.Description)
            if isinstance(value, list):
                with contextlib.suppress(Exception):
                    varset.Value = convert_list_type(value, new_type)
            return True

        # Raw type conversion
        value = varset.Value
        varset.removeProperty("Value")
        varset.addProperty(new_type, "Value", "", varset.Description)
        if value:
            with contextlib.suppress(Exception):
                varset.Value = type(varset.Value)(value)
        return True

    return False


def convert_list_type(data: list, new_type: str) -> list:
    """
    Convert a list of values to a new list with elements cast to a specified type.

    :param list data: The list of values to convert.
    :param str new_type: The type of the new list.
    :return: A new list with the converted values.
    """
    if not data:
        return []
    if new_type == "App::PropertyStringList":
        return [str(item) for item in data]
    if new_type == "App::PropertyIntegerList":
        return [int(item) for item in data]
    if new_type == "App::PropertyFloatList":
        return [float(item) for item in data]
    return []


def export_variables(path: str | Path, doc: Document | None = None) -> bool:
    """
    Export variables to a file.

    :param path: The path to the file where the variables will be exported.
    :param doc: The document where to export the variables. Defaults to ActiveDocument.
    :return: True if the export was successful, False otherwise.
    """
    from .files import save_variables_to_file, VarInfoData

    if not path:
        return False

    path = Path(path)
    doc = doc or App.activeDocument()

    variables = get_vars(doc)

    var_info_list = [
        VarInfoData(
            type=var.var_type,
            name=var.name,
            value=var.value,
            internal_name=var.internal_name,
            description=var.description,
            group=var.group,
            expression=var.expression,
            options=var.options,
            read_only=var.read_only,
            hidden=var.hidden,
            sort_key=var.varset.SortKey,
        )
        for var in variables
    ]

    save_variables_to_file(path, var_info_list)
    return True


def import_variables(path: str | Path, doc: Document | None = None) -> bool:
    """
    Import variables from a file.

    :param path: The path to the file from which the variables will be imported.
    :param doc: The document where to import the variables. Defaults to ActiveDocument.
    :return: True if the import was successful, False otherwise.
    """
    from .files import load_variables_from_file
    from .properties import get_supported_property_types

    if not path:
        return False

    path = Path(path)
    doc = doc or App.activeDocument()

    variables = load_variables_from_file(path)
    supported = get_supported_property_types()

    for var in variables:
        if var.type not in supported:
            App.Console.PrintError(
                f"Variable '{var.name}' type '{var.type}' is not supported. (Not imported)\n",
            )
            continue

        doc_var = Variable(doc, var.name)
        if doc_var.exists():
            if doc_var.var_type != var.type:
                App.Console.PrintError(
                    f"Variable '{var.name}' already exists with a different type. (Not imported)\n",
                )
                continue
        else:
            doc_var.create_if_not_exists(
                var_type=var.type,
                options=var.options,
                description=var.description,
                expression=var.expression,
                group=var.group,
            )

        if var.value is not None and not var.expression:
            try:
                doc_var.value = var.value
            except Exception:  # noqa: BLE001
                App.Console.PrintError(
                    f"Variable '{var.name}' value ({var.value}) is not valid. (Ignored)\n",
                )

        doc_var.read_only = var.read_only
        doc_var.hidden = var.hidden
        doc_var._set_sort_key(var.sort_key)  # noqa: SLF001

    return True


class Variable:
    """
    A wrapper class for a variable.
    """

    _name: str
    _doc: Document
    _obj: DocumentObject | None = None

    def __init__(self, doc: Document, name: str) -> None:
        """
        Initialize a Variable proxy (does not create the variable).

        :param doc: The document associated with the variable.
        :param name: The name of the variable.
        :raises ValueError: If the document is None or the name is invalid.
        """
        if not doc:
            msg = "doc cannot be None"
            raise ValueError(msg)

        name = sanitize_var_name(name)
        self._name = name
        self._doc = doc
        self._obj = get_varset(name, doc)

    def create_if_not_exists(
        self,
        *,
        var_type: str = "App::PropertyLength",
        default: Any = None,
        options: VarOptions = None,
        description: str = "",
        expression: str | None = None,
        group: str = "Default",
    ) -> Variable:
        """
        Create a variable if it doesn't exist.

        If the variable doesn't exist, it is created with the given arguments.
        If the variable already exists, it is not modified.

        :param var_type: The type of the variable, defaults to 'App::PropertyLength'.
        :param default: The default value of the variable, defaults to None.
        :param options: The options for the variable if var_type is 'App::PropertyEnumeration',
                        defaults to None.
        :param description: The description of the variable, defaults to "".
        :param expression: The expression to calculate the value of the variable, defaults to None.
        :return: self
        """
        create_var(
            name=self._name,
            var_type=var_type,
            value=default,
            options=options,
            description=description,
            expression=expression,
            doc=self._doc,
            group=group,
        )
        self._obj = get_varset(self._name, self._doc)
        return self

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> Any:
        return self.varset.Value

    @value.setter
    def value(self, value: Any) -> None:
        varset = self.varset
        attr = varset.Value
        if isinstance(attr, App.Units.Quantity):
            if isinstance(value, str):
                varset.Value = App.Units.Quantity(value)
            elif isinstance(value, tuple):
                varset.Value = App.Units.Quantity(*value)
            else:
                varset.Value = value
        else:
            varset.Value = value

    def rename(self, new_name: str, description: str | None = None) -> bool:
        varset = self.varset
        new_name = sanitize_var_name(new_name)
        actual_name = existing_var_name(new_name, self._doc)

        if actual_name and actual_name.lower() != self._name.lower():
            return False

        varset.Label = new_name
        self._name = new_name
        if description:
            varset.setDocumentationOfProperty("Value", description)
            if hasattr(varset, "Description"):
                varset.Description = description
            if hasattr(varset, "Label2"):
                varset.Label2 = description
        self._doc.recompute()
        return True

    @property
    def options(self) -> list[str]:
        return self.varset.getEnumerationsOfProperty("Value") or []

    @options.setter
    def options(self, options: VarOptions) -> None:
        if callable(options):
            options = options()
        if isinstance(options, (list, tuple)):
            self.varset.Value = options
        else:
            msg = "invalid options type, must be list, tuple or callable returning a list"
            raise TypeError(msg)

    @property
    def expression(self) -> str | None:
        if (varset := self.varset) and varset.ExpressionEngine:
            for prop, expr, *_ in varset.ExpressionEngine:
                if prop == "Value":
                    return expr
        return None

    @expression.setter
    def expression(self, expression: str | None) -> None:
        if not expression:
            self.varset.clearExpression("Value")
        self.varset.setExpression("Value", expression)

    def __repr__(self) -> str:
        return f"Variable(name={self.name}, value={self.value})"

    def exists(self) -> bool:
        try:
            return bool(self.varset)
        except ValueError:
            return False

    def delete(self) -> bool:
        try:
            self._doc.removeObject(self.varset.Name)
            self._obj = None
        except ValueError:
            return False
        return True

    @property
    def dependencies(self) -> list[DocumentObject]:
        return list(set(self.varset.OutList)) or []

    @property
    def references(self) -> list[DocumentObject]:
        return list(set(self.varset.InList)) or []

    @property
    def description(self) -> str:
        varset = self.varset
        return (
            getattr(varset, "Description", "")
            or varset.getDocumentationOfProperty("Value")
            or getattr(varset, "Label2", "")
            or ""
        )

    @description.setter
    def description(self, description: str) -> None:
        varset = self.varset
        varset.setDocumentationOfProperty("Value", description)
        if hasattr(varset, "Description"):
            varset.Description = description
        if hasattr(varset, "Label2"):
            varset.Label2 = description

    @property
    def group(self) -> str:
        return self.varset.VarGroup or "Default"

    @group.setter
    def group(self, group: str) -> None:
        self.varset.VarGroup = (group or "Default").title()

    @property
    def var_type(self) -> str:
        return self.varset.getTypeIdOfProperty("Value")

    @property
    def varset(self) -> DocumentObject | None:
        varset = self._obj
        if not varset:
            self._obj = varset = get_varset(self._name, self._doc)
            if not varset:
                msg = f"Variable {self._name} does not exists"
                raise ValueError(msg)
        return varset

    @property
    def internal_name(self) -> str:
        return self.varset.Name

    @property
    def document(self) -> Document:
        return self._doc

    @property
    def editor_mode(self) -> list[str]:
        return self.varset.getEditorMode("Value")

    @editor_mode.setter
    def editor_mode(self, value: str | list[str]) -> None:
        varset = self.varset
        modes = {
            "ReadOnly": (op.or_, 1),
            "Hidden": (op.or_, 2),
            "-ReadOnly": (op.and_, ~1),
            "-Hidden": (op.and_, ~2),
        }
        if not isinstance(value, list):
            value = [value]
        ops = [modes.get(v) for v in varset.getEditorMode("Value")]
        ops.extend(modes.get(v, (op.or_, 0)) for v in value)
        mode = 0
        for f, v in ops:
            mode = f(mode, v)
        varset.setEditorMode("Value", mode)

    @property
    def read_only(self) -> bool:
        return "ReadOnly" in self.editor_mode

    @read_only.setter
    def read_only(self, ro: bool) -> None:
        self.editor_mode = "ReadOnly" if ro else "-ReadOnly"

    @property
    def hidden(self) -> bool:
        try:
            return self.varset.Hidden
        except AttributeError:
            return False

    @hidden.setter
    def hidden(self, value: bool) -> None:
        varset = self.varset
        if not hasattr(varset, "Hidden"):
            varset.addProperty(
                "App::PropertyBool",
                "Hidden",
                "",
                "Hide variable from UI",
                PropertyMode.Output | PropertyMode.NoRecompute,
            )
        varset.Hidden = value

    @property
    def sort_key(self) -> tuple[str | int, ...]:
        try:
            return (self.group, self.varset.SortKey, self.name)
        except AttributeError:
            return (self.group, 0, self.name)

    def _set_sort_key(self, key: int) -> None:
        varset = self.varset
        if not hasattr(varset, "SortKey"):
            varset.addProperty(
                "App::PropertyInteger",
                "SortKey",
                "",
                "Variable Sort Key",
                PropertyMode.Output | PropertyMode.NoRecompute,
            )
        varset.SortKey = key

    @property
    def group_sort_key(self) -> int:
        try:
            gsk = self.varset.GroupSortKey
            # print(f"DEV: Variable {self.name} accessed group_sort_key: {gsk}")
            return gsk
        except AttributeError:
            print(f"DEV: AttributeError for GroupSortKey on {self.name}. Attempting to initialize.")
            _doc = self.document or App.ActiveDocument
            if hasattr(self.varset, "addProperty") and _doc and not _doc.isRestoring():
                 self.varset.addProperty("App::PropertyInteger", "GroupSortKey", "", "Group Sort Key", PropertyMode.Output | PropertyMode.NoRecompute)
                 # Re-fetch or assign carefully
                 # This might indicate an issue with initial creation or file load
                 # We need to ensure all variables in the same group get the same key
                 # This might be a good place for a "repair" or "ensure consistency" function
                 # For now, let's try to get it based on its current group
                 initial_gsk = _get_or_assign_initial_group_sort_key(self.group, _doc)
                 self.varset.GroupSortKey = initial_gsk
                 print(f"DEV: Initialized and set GroupSortKey for {self.name} to {initial_gsk}")
                 return self.varset.GroupSortKey
            print(f"DEV: Could not initialize GroupSortKey for {self.name}. Returning default 0.")
            return 0 # Default if unable to set

    def reorder(self, delta: float) -> None:
        group = self.group
        group_vars = sorted(v for v in get_vars() if v.group == group)
        for pos, var in enumerate(group_vars):
            var._set_sort_key(pos)  # noqa: SLF001

        seek = self.varset.SortKey + delta
        offset = 0
        ins = -1
        for pos, var in enumerate(v for v in group_vars if v.internal_name != self.internal_name):
            if pos >= seek and offset == 0:
                ins = pos
                offset = 1
            var._set_sort_key(pos + offset)  # noqa: SLF001
        self._set_sort_key(ins if ins > -1 else len(group_vars))

    def __lt__(self, other: Variable) -> bool:
        return self.sort_key < other.sort_key

    def __eq__(self, other: Variable) -> bool:
        if self.exists() and other.exists():
            return self.internal_name == other.internal_name
        return self.name == other.name and self.document == other.document

    @hidden.setter
    def hidden(self, value: bool) -> None:
        varset = self.varset
        if not hasattr(varset, "Hidden"):
            varset.addProperty(
                "App::PropertyBool",
                "Hidden",
                "",
                "Hide variable from UI",
                PropertyMode.Output | PropertyMode.NoRecompute,
            )
        varset.Hidden = value

    def change_var_type(
        self,
        new_type: str,
        converter: Callable | None = None,
    ) -> bool:
        return set_var_type(
            self._name,
            new_type,
            doc=self._doc,
            converter=converter,
        )


def existing_var_name(name: str, doc: Document | None = None) -> str | None:
    """
    Check if a variable name exists in the document (case insensitive).

    :param name: The name of the variable to check.
    :param doc: The document where to search for the variable. Defaults to ActiveDocument.
    :return: The variable name if it exists, None otherwise.
    """
    doc = doc or App.activeDocument()
    name = name.lower()
    for obj in doc.findObjects("App::VarSet"):
        if is_var(obj) and obj.Label.lower() == name:
            return obj.Label
    return None


def reorder_group(group_name_to_move: str, delta: float, doc: Document | None = None) -> bool:
    print(f"DEV: reorder_group called for group '{group_name_to_move}', delta: {delta}")
    _doc = doc or App.ActiveDocument
    if not _doc:
        print("DEV: ERROR - No document in reorder_group")
        return False

    # 1. Get current groups and their sort keys
    #    Store as list of dicts: [{'name': str, 'key': int}]
    #    We need one representative key per group.
    groups_data: dict[str, int] = {}  # group_name -> group_sort_key
    all_vars = get_vars(_doc)
    for var_item in all_vars:
        try:
            gsk = var_item.varset.GroupSortKey
            if var_item.group not in groups_data:
                groups_data[var_item.group] = gsk
            elif groups_data[var_item.group] != gsk:
                # This indicates an inconsistency. For reordering, we might pick one or average,
                # but ideally, all vars in a group have the same GSK.
                # For now, let's assume the first one encountered is "correct" for that group.
                print(
                    f"DEV: WARNING - Inconsistent GroupSortKey for group {var_item.group} during reorder. Using {groups_data[var_item.group]}. Var {var_item.name} has {gsk}"
                )
        except AttributeError:
            print(
                f"DEV: ERROR - Variable {var_item.name} in group {var_item.group} missing GroupSortKey during reorder."
            )
            # Attempt to fix it on the fly - this is risky but might help for older files
            if hasattr(var_item.varset, "addProperty") and not _doc.isRestoring():
                var_item.varset.addProperty(
                    "App::PropertyInteger",
                    "GroupSortKey",
                    "",
                    "Group Sort Key",
                    PropertyMode.Output | PropertyMode.NoRecompute,
                )
                fix_gsk = _get_or_assign_initial_group_sort_key(
                    var_item.group, _doc
                )  # This will try to assign based on current state
                var_item.varset.GroupSortKey = fix_gsk
                groups_data[var_item.group] = fix_gsk  # Add it to our current understanding
                print(f"DEV: Fixed and set GroupSortKey for {var_item.name} to {fix_gsk}")
            else:
                return False  # Cannot proceed if data is corrupt and cannot be fixed

    if not groups_data:
        print("DEV: No groups found to reorder.")
        return False

    # Convert to list of dicts and sort by current key, then name for stability
    sorted_groups = sorted(
        [{"name": g_name, "key": g_key} for g_name, g_key in groups_data.items()],
        key=lambda x: (x["key"], x["name"]),
    )
    print(f"DEV: Groups before reorder: {sorted_groups}")

    # Find the group to move
    current_pos_idx = -1
    for idx, g_data in enumerate(sorted_groups):
        if g_data["name"] == group_name_to_move:
            current_pos_idx = idx
            break

    if current_pos_idx == -1:
        print(f"DEV: ERROR - Group '{group_name_to_move}' not found for reordering.")
        return False

    # Calculate new index
    num_groups = len(sorted_groups)
    if delta == float("-inf"):  # Move to top
        new_pos_idx = 0
    elif delta == float("inf"):  # Move to bottom
        new_pos_idx = num_groups - 1
    else:  # Move up/down by 1
        new_pos_idx = current_pos_idx + int(delta)

    new_pos_idx = max(0, min(new_pos_idx, num_groups - 1))
    print(f"DEV: Moving '{group_name_to_move}' from index {current_pos_idx} to {new_pos_idx}")

    if new_pos_idx == current_pos_idx:
        print("DEV: Group is already in the target position.")
        return False  # No change needed

    # Reorder: remove and insert
    group_to_move_item = sorted_groups.pop(current_pos_idx)
    sorted_groups.insert(new_pos_idx, group_to_move_item)
    print(f"DEV: Groups after reorder (before updating keys): {sorted_groups}")

    # Update GroupSortKey for all variables in all groups based on their new order.
    # And re-normalize keys to be contiguous from 0.
    changes_made = False
    for new_key_idx, group_data_item in enumerate(sorted_groups):
        target_group_name = group_data_item["name"]
        # Update all vars belonging to this group
        for var_item in all_vars:  # Iterate through all_vars again
            if var_item.group == target_group_name:
                if not hasattr(var_item.varset, "GroupSortKey"):  # Should exist by now
                    print(
                        f"DEV: ERROR - Varset for {var_item.name} missing GroupSortKey during final update."
                    )
                    # Attempt to add it again, though this indicates a deeper issue
                    var_item.varset.addProperty(
                        "App::PropertyInteger",
                        "GroupSortKey",
                        "",
                        "Group Sort Key",
                        PropertyMode.Output | PropertyMode.NoRecompute,
                    )

                if var_item.varset.GroupSortKey != new_key_idx:
                    print(
                        f"DEV: Updating GroupSortKey for var '{var_item.name}' (group '{target_group_name}') from {var_item.varset.GroupSortKey} to {new_key_idx}"
                    )
                    var_item.varset.GroupSortKey = new_key_idx
                    changes_made = True

    if changes_made:
        print("DEV: GroupSortKeys updated. Requesting document recompute.")
        _doc.recompute()  # Important to persist changes
    else:
        print("DEV: No actual GroupSortKey values needed to be changed after reordering logic.")

    return changes_made
