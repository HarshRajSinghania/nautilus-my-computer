"""Selection bridge between Column View and Nautilus's native List/Grid view (#178).

Nautilus stays the authority for slot and history selection. List and Grid share
one NautilusViewModel per slot (a Gtk.SelectionModel) that stays alive, hidden,
while Column View shows. This module only reads it, and writes Column View's
selection into it by URI (Nautilus.FileInfo.get_uri() matched against model
positions, never by display name).

The only state kept is `_pending`: a temporary set of URIs waiting for the model
of the matching folder to load. It is never applied to a model showing another
folder and is dropped on the next location change or the next selection change.
"""

from gi.repository import Gio, GLib, Gtk, Nautilus

from . import selection
from .common import _log


def _norm(uri: str) -> str:
    return Gio.File.new_for_uri(uri).get_uri()


def _item_uri(obj) -> str | None:
    if isinstance(obj, Gtk.TreeListRow):
        obj = obj.get_item()
    info = obj.get_property("file") if obj is not None else None
    return info.get_uri() if isinstance(info, Nautilus.FileInfo) else None


class NativeBridge:
    """Per-slot access to the native view's selection."""

    def __init__(self, slot, on_native_selected) -> None:
        self._slot = slot
        # Called with the native URIs (possibly none) when the native selection
        # changes by itself or a load finishes.
        self._on_native_selected = on_native_selected
        self._view = None
        self._model = None
        self._ids: list[int] = []
        self._writing = False
        self._pending = selection.PendingSelection()
        slot.connect("notify::location", self._on_location_changed)
        slot.connect("notify::loading", self._on_loading_changed)

    # model access

    def _find_view(self):
        stack = None
        for w in _walk(self._slot):
            if isinstance(w, Gtk.Stack) and w.get_child_by_name("mc-column") is not None:
                stack = w
                break
        skip = stack.get_child_by_name("mc-column") if stack else None
        for w in _walk(self._slot):
            if not isinstance(w, (Gtk.ListView, Gtk.GridView)):
                continue
            model = w.get_model()
            if model is None or type(model).__name__ != "NautilusViewModel":
                continue
            p = w
            while p is not None and p is not skip:
                p = p.get_parent()
            if p is None:
                return w
        return None

    def model(self):
        """The slot's native model, rebound when the view or its model changes.
        Strong references are held: PyGObject wrapper identity is only stable
        while one is alive."""
        view = self._view
        if view is not None and view.get_root() is not None and view.get_model() is self._model:
            return self._model
        view = self._find_view()
        model = view.get_model() if view is not None else None
        if model is not self._model:
            loc = self._slot.get_property("location")
            reason = (
                "first bind"
                if self._model is None
                else "view detached"
                if self._view is None or self._view.get_root() is None
                else "model replaced"
            )
            _log(
                f"native_selection: bind slot={id(self._slot) & 0xFFFF:04x} "
                f"folder={loc.get_uri() if loc else None!r} reason={reason}"
            )
            self._unhook()
            self._model = model
            if model is not None:
                self._ids = [model.connect("selection-changed", self._on_selection_changed)]
        self._view = view
        return model

    def _unhook(self) -> None:
        if self._model is not None:
            for handler in self._ids:
                self._model.disconnect(handler)
        self._ids = []
        self._model = None

    def shows(self, folder_uri: str) -> bool:
        loc = self._slot.get_property("location")
        return loc is not None and loc.equal(Gio.File.new_for_uri(folder_uri))

    def _loading(self) -> bool:
        return bool(self._slot.get_property("loading"))

    def read(self) -> list[str]:
        model = self.model()
        if model is None:
            return []
        bits = model.get_selection()
        uris = (_item_uri(model.get_item(bits.get_nth(i))) for i in range(bits.get_size()))
        return [u for u in uris if u]

    def _available(self, model) -> frozenset[str]:
        uris = (_item_uri(model.get_item(i)) for i in range(model.get_n_items()))
        return frozenset(_norm(u) for u in uris if u)

    def _write(self, model, uris: frozenset[str]) -> None:
        """Select exactly `uris`, all known to be in the model."""
        n = model.get_n_items()
        if n == 0:
            return
        selected = Gtk.Bitset.new_empty()
        for i in range(n):
            uri = _item_uri(model.get_item(i))
            if uri is not None and _norm(uri) in uris:
                selected.add(i)
        self._writing = True
        try:
            model.set_selection(selected, Gtk.Bitset.new_range(0, n))
        finally:
            self._writing = False
        _log(f"native_selection: wrote {len(uris)} of {n} rows")

    # Column View -> native

    def push(self, folder_uri: str, uris: list[str]) -> None:
        """Column selection changed in the column showing `folder_uri`. Written
        only when the native model shows that same folder; an ancestor column
        leaves it alone (see carry)."""
        if not self.shows(folder_uri):
            return
        _log(f"native_selection: push {len(uris)} for {folder_uri!r}")
        self._set_pending(folder_uri, uris)

    def carry(self, folder_uri: str, uris: list[str]) -> None:
        """Leaving Column View with an ancestor column selected: navigate the
        slot to that column's folder, then apply once it has loaded."""
        self._set_pending(folder_uri, uris)
        if not self.shows(folder_uri):
            _log(f"native_selection: carry {len(uris)} via open-location {folder_uri!r}")
            self._slot.activate_action("slot.open-location", GLib.Variant("s", folder_uri))

    def expect(self, folder_uri: str, uris: list[str]) -> None:
        """Column View is about to navigate the slot to `folder_uri` and wants
        `uris` selected there. Applied after the load, on top of Nautilus's own
        default (it selects the folder it came from when going up)."""
        self._set_pending(folder_uri, uris)

    def _set_pending(self, folder_uri: str, uris: list[str]) -> None:
        self._pending.set(folder_uri, (_norm(u) for u in uris))
        self._try_apply(final=False)

    def _try_apply(self, *, final: bool) -> None:
        folder = self._pending.folder
        if folder is None or not self.shows(folder):
            return
        if self._loading() and not final:
            return
        model = self.model()
        if model is None:
            return
        ready = self._pending.resolve(self._available(model), final=final)
        if ready is not None:
            self._write(model, ready)

    # slot and model signals

    def _on_loading_changed(self, _slot, _pspec) -> None:
        if self._loading():
            return
        # Nautilus has applied its own restored selection by now (end_loading
        # runs before this notify), so ours goes on top exactly once.
        self._try_apply(final=True)
        self._pending.drop()
        self._report()

    def _on_selection_changed(self, _model, _pos, _n) -> None:
        if self._writing or self._loading():
            return
        # A selection made natively wins over anything still pending.
        self._pending.drop()
        self._report()

    def _report(self) -> None:
        if selection.adopt_native(
            loading=self._loading(), writing=self._writing, pending=self._pending.active
        ):
            self._on_native_selected(self.read())

    def _on_location_changed(self, _slot, _pspec) -> None:
        folder = self._pending.folder
        if folder is not None and not self.shows(folder):
            self._pending.drop()
        # Do not keep Nautilus's view and model alive across a navigation: it
        # replaces them itself, and a referenced leftover still receives the
        # shared model's items-changed with no parent.
        self._unhook()
        self._view = None


def _walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _walk(child)
        child = child.get_next_sibling()
