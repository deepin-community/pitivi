# -*- coding: utf-8 -*-
# Pitivi video editor
# Copyright (C) 2010 Thibault Saunier <tsaunier@gnome.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, see <http://www.gnu.org/licenses/>.
"""Widgets to control clips properties."""
import bisect
import os
from gettext import gettext as _

import cairo
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GES
from gi.repository import Gst
from gi.repository import GstController
from gi.repository import Gtk

from pitivi.clip_properties.alignment import AlignmentEditor
from pitivi.clip_properties.color import ColorProperties
from pitivi.clip_properties.title import TitleProperties
from pitivi.configure import get_pixmap_dir
from pitivi.configure import get_ui_dir
from pitivi.effects import EffectsPopover
from pitivi.effects import EffectsPropertiesManager
from pitivi.effects import HIDDEN_EFFECTS
from pitivi.undo.timeline import CommitTimelineFinalizingAction
from pitivi.utils.custom_effect_widgets import setup_custom_effect_widgets
from pitivi.utils.loggable import Loggable
from pitivi.utils.misc import disconnect_all_by_func
from pitivi.utils.pipeline import PipelineError
from pitivi.utils.timeline import SELECT
from pitivi.utils.ui import disable_scroll
from pitivi.utils.ui import EFFECT_TARGET_ENTRY
from pitivi.utils.ui import PADDING
from pitivi.utils.ui import SPACING

(COL_ACTIVATED,
 COL_TYPE,
 COL_BIN_DESCRIPTION_TEXT,
 COL_NAME_TEXT,
 COL_DESC_TEXT,
 COL_TRACK_EFFECT) = list(range(6))

FOREGROUND_DEFAULT_COLOR = 0xFFFFFFFF  # White
BACKGROUND_DEFAULT_COLOR = 0x00000000  # Transparent
DEFAULT_FONT_DESCRIPTION = "Sans 36"
DEFAULT_VALIGNMENT = "absolute"
DEFAULT_HALIGNMENT = "absolute"


class ClipProperties(Gtk.ScrolledWindow, Loggable):
    """Widget for configuring the selected clip.

    Attributes:
        app (Pitivi): The app.
    """

    def __init__(self, app):
        Gtk.ScrolledWindow.__init__(self)
        Loggable.__init__(self)
        self.app = app

        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        viewport = Gtk.Viewport()
        viewport.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        viewport.show()
        self.add(viewport)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.show()
        viewport.add(vbox)

        self.clips_box = Gtk.Box()
        self.clips_box.set_orientation(Gtk.Orientation.VERTICAL)
        self.clips_box.show()
        vbox.pack_start(self.clips_box, False, False, 0)

        self.transformation_expander = TransformationProperties(app)
        self.transformation_expander.set_vexpand(False)
        vbox.pack_start(self.transformation_expander, False, False, 0)

        self.title_expander = TitleProperties(app)
        self.title_expander.set_vexpand(False)
        vbox.pack_start(self.title_expander, False, False, 0)

        self.color_expander = ColorProperties(app)
        self.color_expander.set_vexpand(False)
        vbox.pack_start(self.color_expander, False, False, 0)

        self.effect_expander = EffectProperties(app)
        self.effect_expander.set_vexpand(False)
        vbox.pack_start(self.effect_expander, False, False, 0)

        self.helper_box = self.create_helper_box()
        self.clips_box.pack_start(self.helper_box, False, False, 0)

        self.transformation_expander.set_source(None)
        self.title_expander.set_source(None)
        self.color_expander.set_source(None)
        self.effect_expander.set_clip(None)

        self._project = None
        self._selection = None

    def create_helper_box(self):
        """Creates the widgets to display when no clip is selected."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.props.margin = PADDING

        label = Gtk.Label(label=_("Select a clip on the timeline to configure its properties and effects or create a new clip:"))
        label.set_line_wrap(True)
        label.set_xalign(0)
        box.pack_start(label, False, False, SPACING)

        title_button = Gtk.Button()
        title_button.set_label(_("Create a title clip"))
        title_button.connect("clicked", self.create_title_clip_cb)
        box.pack_start(title_button, False, False, SPACING)

        color_button = Gtk.Button()
        color_button.set_label(_("Create a color clip"))
        color_button.connect("clicked", self.create_color_clip_cb)
        box.pack_start(color_button, False, False, SPACING)

        box.show_all()
        return box

    def create_title_clip_cb(self, unused_button):
        title_clip = GES.TitleClip()
        duration = self.app.settings.titleClipLength * Gst.MSECOND
        title_clip.set_duration(duration)
        with self.app.action_log.started("add title clip", toplevel=True):
            self.app.gui.editor.timeline_ui.insert_clips_on_first_layer([
                title_clip])
            # Now that the clip is inserted in the timeline, it has a source which
            # can be used to set its properties.
            source = title_clip.get_children(False)[0]
            properties = {"text": "",
                          "foreground-color": BACKGROUND_DEFAULT_COLOR,
                          "color": FOREGROUND_DEFAULT_COLOR,
                          "font-desc": DEFAULT_FONT_DESCRIPTION,
                          "valignment": DEFAULT_VALIGNMENT,
                          "halignment": DEFAULT_HALIGNMENT}
            for prop, value in properties.items():
                res = source.set_child_property(prop, value)
                assert res, prop
        self._selection.set_selection([title_clip], SELECT)

    def create_color_clip_cb(self, unused_widget):
        color_clip = GES.TestClip.new()
        duration = self.app.settings.ColorClipLength * Gst.MSECOND
        color_clip.set_duration(duration)
        color_clip.set_vpattern(GES.VideoTestPattern.SOLID_COLOR)
        color_clip.set_supported_formats(GES.TrackType.VIDEO)
        with self.app.action_log.started("add color clip",
                                         finalizing_action=CommitTimelineFinalizingAction(self._project.pipeline),
                                         toplevel=True):
            self.app.gui.editor.timeline_ui.insert_clips_on_first_layer([color_clip])
        self._selection.set_selection([color_clip], SELECT)

    def set_project(self, project, timeline_ui):
        if self._project:
            self._selection.disconnect_by_func(self._selection_changed_cb)
            self._selection = None
        if project:
            self._selection = timeline_ui.timeline.selection
            self._selection.connect("selection-changed", self._selection_changed_cb)
        self._project = project

    def _selection_changed_cb(self, selection):
        selected_clips = selection.selected
        single_clip_selected = len(selected_clips) == 1
        self.helper_box.set_visible(not single_clip_selected)

        video_source = None
        title_source = None
        color_clip_source = None
        ges_clip = None
        if single_clip_selected:
            ges_clip = list(selected_clips)[0]

            for child in ges_clip.get_children(False):
                if isinstance(child, GES.VideoSource):
                    video_source = child

                if isinstance(child, GES.TitleSource):
                    title_source = child
                elif isinstance(child, GES.VideoTestSource):
                    color_clip_source = child

        self.transformation_expander.set_source(video_source)
        self.title_expander.set_source(title_source)
        self.color_expander.set_source(color_clip_source)
        self.effect_expander.set_clip(ges_clip)

        self.app.gui.editor.viewer.overlay_stack.select(video_source)


class EffectProperties(Gtk.Expander, Loggable):
    """Widget for viewing a list of effects and configuring them.

    Attributes:
        app (Pitivi): The app.
        clip (GES.Clip): The clip being configured.
    """

    def __init__(self, app):
        Gtk.Expander.__init__(self)

        self.set_expanded(True)
        self.set_label(_("Effects"))
        Loggable.__init__(self)

        self.app = app
        self.clip = None

        self.effects_properties_manager = EffectsPropertiesManager(app)
        setup_custom_effect_widgets(self.effects_properties_manager)

        self.drag_lines_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            os.path.join(get_pixmap_dir(), "grip-lines-solid.svg"),
            15, 15)

        self.expander_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.effects_listbox = Gtk.ListBox()

        placeholder_label = Gtk.Label(
            _("To apply an effect to the clip, drag it from the Effect Library "
              "or use the button below."))
        placeholder_label.set_line_wrap(True)
        placeholder_label.show()
        self.effects_listbox.set_placeholder(placeholder_label)

        # Add effect popover button
        self.effect_popover = EffectsPopover(app)
        self.add_effect_button = Gtk.MenuButton(_("Add Effect"))
        self.add_effect_button.set_popover(self.effect_popover)
        self.add_effect_button.props.halign = Gtk.Align.CENTER

        self.drag_dest_set(Gtk.DestDefaults.DROP, [EFFECT_TARGET_ENTRY],
                           Gdk.DragAction.COPY)

        self.expander_box.pack_start(self.effects_listbox, False, False, 0)
        self.expander_box.pack_start(self.add_effect_button, False, False, PADDING)

        self.add(self.expander_box)

        # Connect all the widget signals
        self.connect("drag-motion", self._drag_motion_cb)
        self.connect("drag-leave", self._drag_leave_cb)
        self.connect("drag-data-received", self._drag_data_received_cb)

        self.add_effect_button.connect("toggled", self._add_effect_button_cb)

        self.show_all()

    def _add_effect_button_cb(self, button):
        # MenuButton interacts directly with the popover, bypassing our subclassed method
        if button.props.active:
            self.effect_popover.search_entry.set_text("")

    def _create_effect_row(self, effect):
        effect_info = self.app.effects.get_info(effect.props.bin_description)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        row_drag_icon = Gtk.Image.new_from_pixbuf(self.drag_lines_pixbuf)

        toggle = Gtk.CheckButton()
        toggle.props.active = effect.props.active

        effect_label = Gtk.Label(effect_info.human_name)
        effect_label.set_tooltip_text(effect_info.description)

        # Set up revealer + expander
        effect_config_ui = self.effects_properties_manager.get_effect_configuration_ui(
            effect)
        config_ui_revealer = Gtk.Revealer()
        config_ui_revealer.add(effect_config_ui)

        expander = Gtk.Expander()
        expander.set_label_widget(effect_label)
        expander.props.valign = Gtk.Align.CENTER
        expander.props.vexpand = True

        config_ui_revealer.props.halign = Gtk.Align.CENTER
        expander.connect("notify::expanded", self._toggle_expander_cb, config_ui_revealer)

        remove_effect_button = Gtk.Button.new_from_icon_name("window-close",
                                                             Gtk.IconSize.BUTTON)
        remove_effect_button.props.margin_right = PADDING

        row_widgets_box = Gtk.Box()
        row_widgets_box.pack_start(row_drag_icon, False, False, PADDING)
        row_widgets_box.pack_start(toggle, False, False, PADDING)
        row_widgets_box.pack_start(expander, True, True, PADDING)
        row_widgets_box.pack_end(remove_effect_button, False, False, 0)

        vbox.pack_start(row_widgets_box, False, False, 0)
        vbox.pack_start(config_ui_revealer, False, False, 0)

        event_box = Gtk.EventBox()
        event_box.add(vbox)

        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        row.effect = effect
        row.toggle = toggle
        row.add(event_box)

        # Set up drag&drop
        event_box.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,
                                  [EFFECT_TARGET_ENTRY], Gdk.DragAction.MOVE)
        event_box.connect("drag-begin", self._drag_begin_cb)
        event_box.connect("drag-data-get", self._drag_data_get_cb)

        row.drag_dest_set(Gtk.DestDefaults.ALL, [EFFECT_TARGET_ENTRY],
                          Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
        row.connect("drag-data-received", self._drag_data_received_cb)

        remove_effect_button.connect("clicked", self._remove_button_cb, row)
        toggle.connect("toggled", self._effect_active_toggle_cb, row)

        return row

    def _update_listbox(self):
        for row in self.effects_listbox.get_children():
            self.effects_listbox.remove(row)

        for effect in self.clip.get_top_effects():
            if effect.props.bin_description in HIDDEN_EFFECTS:
                continue
            effect_row = self._create_effect_row(effect)
            self.effects_listbox.add(effect_row)

        self.effects_listbox.show_all()

    def _toggle_expander_cb(self, expander, unused_prop, revealer):
        revealer.props.reveal_child = expander.props.expanded

    def _get_effect_row(self, effect):
        for row in self.effects_listbox.get_children():
            if row.effect == effect:
                return row
        return None

    def _add_effect_row(self, effect):
        row = self._create_effect_row(effect)
        self.effects_listbox.add(row)
        self.effects_listbox.show_all()

    def _remove_effect_row(self, effect):
        row = self._get_effect_row(effect)
        self.effects_listbox.remove(row)

    def _move_effect_row(self, effect, new_index):
        row = self._get_effect_row(effect)
        self.effects_listbox.remove(row)
        self.effects_listbox.insert(row, new_index)

    def _remove_button_cb(self, button, row):
        effect = row.effect
        self._remove_effect(effect)

    def _remove_effect(self, effect):
        pipeline = self.app.project_manager.current_project.pipeline
        with self.app.action_log.started("remove effect",
                                         finalizing_action=CommitTimelineFinalizingAction(pipeline),
                                         toplevel=True):
            effect.get_parent().remove(effect)

    def _effect_active_toggle_cb(self, toggle, row):
        effect = row.effect
        pipeline = self.app.project_manager.current_project.pipeline
        with self.app.action_log.started("change active state",
                                         finalizing_action=CommitTimelineFinalizingAction(pipeline),
                                         toplevel=True):
            effect.props.active = toggle.props.active

    def set_clip(self, clip):
        if self.clip:
            self.clip.disconnect_by_func(self._track_element_added_cb)
            self.clip.disconnect_by_func(self._track_element_removed_cb)
            for track_element in self.clip.get_children(recursive=True):
                if isinstance(track_element, GES.BaseEffect):
                    self._disconnect_from_track_element(track_element)

        self.clip = clip
        if self.clip:
            self.clip.connect("child-added", self._track_element_added_cb)
            self.clip.connect("child-removed", self._track_element_removed_cb)
            for track_element in self.clip.get_children(recursive=True):
                if isinstance(track_element, GES.BaseEffect):
                    self._connect_to_track_element(track_element)

            self._update_listbox()
            self.show()
        else:
            self.hide()

    def _track_element_added_cb(self, unused_clip, track_element):
        if isinstance(track_element, GES.BaseEffect):
            self._connect_to_track_element(track_element)
            self._add_effect_row(track_element)

    def _connect_to_track_element(self, track_element):
        track_element.connect("notify::active", self._notify_active_cb)
        track_element.connect("notify::priority", self._notify_priority_cb)

    def _disconnect_from_track_element(self, track_element):
        track_element.disconnect_by_func(self._notify_active_cb)
        track_element.disconnect_by_func(self._notify_priority_cb)

    def _notify_active_cb(self, track_element, unused_param_spec):
        row = self._get_effect_row(track_element)
        row.toggle.props.active = track_element.props.active

    def _notify_priority_cb(self, track_element, unused_param_spec):
        index = self.clip.get_top_effect_index(track_element)
        row = self.effects_listbox.get_row_at_index(index)

        if not row:
            return

        if row.effect != track_element:
            self._move_effect_row(track_element, index)

    def _track_element_removed_cb(self, unused_clip, track_element):
        if isinstance(track_element, GES.BaseEffect):
            self._disconnect_from_track_element(track_element)
            self._remove_effect_row(track_element)

    def _drag_begin_cb(self, eventbox, context):
        """Draws the drag icon."""
        row = eventbox.get_parent()
        alloc = row.get_allocation()

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, alloc.width, alloc.height)
        ctx = cairo.Context(surface)

        row.draw(ctx)
        ctx.paint_with_alpha(0.35)

        Gtk.drag_set_icon_surface(context, surface)

    def _drag_data_get_cb(self, eventbox, drag_context, selection_data, unused_info, unused_timestamp):
        row = eventbox.get_parent()
        effect_info = self.app.effects.get_info(row.effect.props.bin_description)
        effect_name = effect_info.human_name

        data = bytes(effect_name, "UTF-8")
        selection_data.set(drag_context.list_targets()[0], 0, data)

    def _drag_motion_cb(self, unused_widget, unused_drag_context, unused_x, y, unused_timestamp):
        """Highlights some widgets to indicate it can receive drag&drop."""
        self.debug(
            "Something is being dragged in the clip properties' effects list")
        row = self.effects_listbox.get_row_at_y(y)
        if row:
            self.effects_listbox.drag_highlight_row(row)
            self.expander_box.drag_unhighlight()
        else:
            self.effects_listbox.drag_highlight()

    def _drag_leave_cb(self, unused_widget, drag_context, unused_timestamp):
        """Unhighlights the widgets which can receive drag&drop."""
        self.debug(
            "The item being dragged has left the clip properties' effects list")

        self.effects_listbox.drag_unhighlight_row()
        self.effects_listbox.drag_unhighlight()

    def _drag_data_received_cb(self, widget, drag_context, unused_x, y, selection_data, unused_info, timestamp):
        if not self.clip:
            # Indicate that a drop will not be accepted.
            Gdk.drag_status(drag_context, 0, timestamp)
            return

        if self.effects_listbox.get_row_at_y(y):
            # Drop happened inside the lisbox
            drop_index = widget.get_index()
        else:
            drop_index = len(self.effects_listbox.get_children()) - 1

        if drag_context.get_suggested_action() == Gdk.DragAction.COPY:
            # An effect dragged probably from the effects list.
            factory_name = str(selection_data.get_data(), "UTF-8")

            self.debug("Effect dragged at position %s", drop_index)
            effect_info = self.app.effects.get_info(factory_name)
            pipeline = self.app.project_manager.current_project.pipeline
            with self.app.action_log.started("add effect",
                                             finalizing_action=CommitTimelineFinalizingAction(
                                                 pipeline),
                                             toplevel=True):
                effect = self.clip.ui.add_effect(effect_info)
                if effect:
                    self.clip.set_top_effect_index(effect, drop_index)

        elif drag_context.get_suggested_action() == Gdk.DragAction.MOVE:
            # An effect dragged from the same listbox to change its position.
            source_eventbox = Gtk.drag_get_source_widget(drag_context)
            source_row = source_eventbox.get_parent()
            source_index = source_row.get_index()

            self._move_effect(self.clip, source_index, drop_index)

        drag_context.finish(True, False, timestamp)

    def _move_effect(self, clip, source_index, drop_index):
        # Handle edge cases
        if drop_index < 0:
            drop_index = 0
        if drop_index > len(clip.get_top_effects()) - 1:
            drop_index = len(clip.get_top_effects()) - 1
        if source_index == drop_index:
            # Noop.
            return

        effects = clip.get_top_effects()
        effect = effects[source_index]
        pipeline = self.app.project_manager.current_project.pipeline

        with self.app.action_log.started("move effect",
                                         finalizing_action=CommitTimelineFinalizingAction(
                                             pipeline),
                                         toplevel=True):
            clip.set_top_effect_index(effect, drop_index)


class TransformationProperties(Gtk.Expander, Loggable):
    """Widget for configuring the placement and size of the clip."""

    def __init__(self, app):
        Gtk.Expander.__init__(self)
        Loggable.__init__(self)
        self.app = app
        self._project = None
        self.source = None
        self.spin_buttons = {}
        self.spin_buttons_handler_ids = {}
        self.set_label(_("Transformation"))
        self.set_expanded(True)

        self.builder = Gtk.Builder()
        self.builder.add_from_file(os.path.join(get_ui_dir(),
                                                "cliptransformation.ui"))

        alignment_editor_container = self.builder.get_object("clip_alignment")
        self.alignment_editor = AlignmentEditor()
        self.alignment_editor.connect("align", self.__alignment_editor_align_cb)
        alignment_editor_container.pack_start(self.alignment_editor, True, True, 0)

        self.__control_bindings = {}
        # Used to make sure self.__control_bindings_changed doesn't get called
        # when bindings are changed from this class
        self.__own_bindings_change = False
        self.add(self.builder.get_object("transform_box"))

        self._init_buttons()
        self.show_all()
        self.hide()

        self.app.project_manager.connect_after(
            "new-project-loaded", self._new_project_loaded_cb)
        self.app.project_manager.connect_after(
            "project-closed", self.__project_closed_cb)

    def _new_project_loaded_cb(self, unused_project_manager, project):
        if self._project:
            self._project.pipeline.disconnect_by_func(self._position_cb)

        self._project = project
        if project:
            self._project.pipeline.connect("position", self._position_cb)

    def __project_closed_cb(self, unused_project_manager, unused_project):
        self._project = None

    def __alignment_editor_align_cb(self, widget):
        """Callback method to align a clip from the AlignmentEditor widget."""
        x, y = self.alignment_editor.get_clip_position(self._project, self.source)
        with self.app.action_log.started("Position change",
                                         finalizing_action=CommitTimelineFinalizingAction(self._project.pipeline),
                                         toplevel=True):
            self.__set_prop("posx", x)
            self.__set_prop("posy", y)

    def _init_buttons(self):
        clear_button = self.builder.get_object("clear_button")
        clear_button.connect("clicked", self._default_values_cb)

        self._activate_keyframes_btn = self.builder.get_object(
            "activate_keyframes_button")
        self._activate_keyframes_btn.connect(
            "toggled", self.__show_keyframes_toggled_cb)

        self._next_keyframe_btn = self.builder.get_object(
            "next_keyframe_button")
        self._next_keyframe_btn.connect(
            "clicked", self.__go_to_keyframe_cb, True)
        self._next_keyframe_btn.set_sensitive(False)

        self._prev_keyframe_btn = self.builder.get_object(
            "prev_keyframe_button")
        self._prev_keyframe_btn.connect(
            "clicked", self.__go_to_keyframe_cb, False)
        self._prev_keyframe_btn.set_sensitive(False)

        self.__setup_spin_button("xpos_spinbtn", "posx")
        self.__setup_spin_button("ypos_spinbtn", "posy")

        self.__setup_spin_button("width_spinbtn", "width")
        self.__setup_spin_button("height_spinbtn", "height")

    def __get_keyframes_timestamps(self):
        keyframes_ts = []
        for prop in ["posx", "posy", "width", "height"]:
            prop_keyframes = self.__control_bindings[prop].props.control_source.get_all(
            )
            keyframes_ts.extend(
                [keyframe.timestamp for keyframe in prop_keyframes])

        return sorted(set(keyframes_ts))

    def __go_to_keyframe_cb(self, unused_button, next_keyframe):
        assert self.__control_bindings
        start = self.source.props.start
        in_point = self.source.props.in_point
        pipeline = self._project.pipeline
        position = pipeline.get_position() - start + in_point
        keyframes_ts = self.__get_keyframes_timestamps()
        if next_keyframe:
            i = bisect.bisect_right(keyframes_ts, position)
        else:
            i = bisect.bisect_left(keyframes_ts, position) - 1
        i = max(0, min(i, len(keyframes_ts) - 1))
        seekval = keyframes_ts[i] + start - in_point
        pipeline.simple_seek(seekval)

    def __show_keyframes_toggled_cb(self, unused_button):
        if self._activate_keyframes_btn.props.active:
            self.__set_control_bindings()
        self.__update_keyframes_ui()

    def __update_keyframes_ui(self):
        if self.__source_uses_keyframes():
            self._activate_keyframes_btn.props.label = "???"
        else:
            self._activate_keyframes_btn.props.label = "???"
            self._activate_keyframes_btn.props.active = False

        if not self._activate_keyframes_btn.props.active:
            self._prev_keyframe_btn.set_sensitive(False)
            self._next_keyframe_btn.set_sensitive(False)
            if self.__source_uses_keyframes():
                self._activate_keyframes_btn.set_tooltip_text(
                    _("Show keyframes"))
            else:
                self._activate_keyframes_btn.set_tooltip_text(
                    _("Activate keyframes"))
            self.source.ui_element.show_default_keyframes()
        else:
            self._prev_keyframe_btn.set_sensitive(True)
            self._next_keyframe_btn.set_sensitive(True)
            self._activate_keyframes_btn.set_tooltip_text(_("Hide keyframes"))
            self.source.ui_element.show_multiple_keyframes(
                list(self.__control_bindings.values()))

    def __update_control_bindings(self):
        self.__control_bindings = {}
        if self.__source_uses_keyframes():
            self.__set_control_bindings()

    def __source_uses_keyframes(self):
        if self.source is None:
            return False

        for prop in ["posx", "posy", "width", "height"]:
            binding = self.source.get_control_binding(prop)
            if binding is None:
                return False

        return True

    def __remove_control_bindings(self):
        for propname, binding in self.__control_bindings.items():
            control_source = binding.props.control_source
            # control_source.unset_all() can't be used here as it doesn't emit
            # the 'value-removed' signal, so the undo system wouldn't notice
            # the removed keyframes
            keyframes_ts = [
                keyframe.timestamp for keyframe in control_source.get_all()]
            for ts in keyframes_ts:
                control_source.unset(ts)
            self.__own_bindings_change = True
            self.source.remove_control_binding(propname)
            self.__own_bindings_change = False
        self.__control_bindings = {}

    def __set_control_bindings(self):
        adding_kfs = not self.__source_uses_keyframes()

        if adding_kfs:
            self.app.action_log.begin("Transformation properties keyframes activate",
                                      toplevel=True)

        for prop in ["posx", "posy", "width", "height"]:
            binding = self.source.get_control_binding(prop)

            if not binding:
                control_source = GstController.InterpolationControlSource()
                control_source.props.mode = GstController.InterpolationMode.LINEAR
                self.__own_bindings_change = True
                self.source.set_control_source(
                    control_source, prop, "direct-absolute")
                self.__own_bindings_change = False
                self.__set_default_keyframes_values(control_source, prop)

                binding = self.source.get_control_binding(prop)
            self.__control_bindings[prop] = binding

        if adding_kfs:
            self.app.action_log.commit(
                "Transformation properties keyframes activate")

    def __set_default_keyframes_values(self, control_source, prop):
        res, val = self.source.get_child_property(prop)
        assert res
        control_source.set(self.source.props.in_point, val)
        control_source.set(self.source.props.in_point +
                           self.source.props.duration, val)

    def _default_values_cb(self, unused_widget):
        with self.app.action_log.started("Transformation properties reset default",
                                         finalizing_action=CommitTimelineFinalizingAction(
                                             self._project.pipeline),
                                         toplevel=True):
            if self.__source_uses_keyframes():
                self.__remove_control_bindings()

            for prop in ["posx", "posy", "width", "height"]:
                self.source.set_child_property(
                    prop, self.source.ui.default_position[prop])

        self.__update_keyframes_ui()

    def __get_source_property(self, prop):
        if self.__source_uses_keyframes():
            try:
                position = self._project.pipeline.get_position()
                start = self.source.props.start
                in_point = self.source.props.in_point
                duration = self.source.props.duration

                # If the position is outside of the clip, take the property
                # value at the start/end (whichever is closer) of the clip.
                source_position = max(
                    0, min(position - start, duration - 1)) + in_point
                value = self.__control_bindings[prop].get_value(
                    source_position)
                res = value is not None
                return res, value
            except PipelineError:
                pass

        return self.source.get_child_property(prop)

    def _position_cb(self, unused_pipeline, unused_position):
        if not self.__source_uses_keyframes():
            return

        for prop in ["posx", "posy", "width", "height"]:
            self.__update_spin_btn(prop)
        # Keep the overlay stack in sync with the spin buttons values
        self.app.gui.editor.viewer.overlay_stack.update(self.source)

    def __source_property_changed_cb(self, unused_source, unused_element, param):
        self.__update_spin_btn(param.name)

    def __update_spin_btn(self, prop):
        assert self.source

        try:
            spin = self.spin_buttons[prop]
            spin_handler_id = self.spin_buttons_handler_ids[prop]
        except KeyError:
            return

        res, value = self.__get_source_property(prop)
        assert res
        if spin.get_value() != value:
            # Make sure self._on_value_changed_cb doesn't get called here. If that
            # happens, we might have unintended keyframes added.
            with spin.handler_block(spin_handler_id):
                spin.set_value(value)

    def _control_bindings_changed(self, unused_track_element, unused_binding):
        if self.__own_bindings_change:
            # Do nothing if the change occurred from this class
            return

        self.__update_control_bindings()
        self.__update_keyframes_ui()

    def __set_prop(self, prop, value):
        assert self.source

        if self.__source_uses_keyframes():
            try:
                position = self._project.pipeline.get_position()
                start = self.source.props.start
                in_point = self.source.props.in_point
                duration = self.source.props.duration
                if position < start or position > start + duration:
                    return
                source_position = position - start + in_point

                self.__control_bindings[prop].props.control_source.set(
                    source_position, value)
            except PipelineError:
                self.warning("Could not get pipeline position")
                return
        else:
            self.source.set_child_property(prop, value)

    def __setup_spin_button(self, widget_name, property_name):
        """Creates a SpinButton for editing a property value."""
        spinbtn = self.builder.get_object(widget_name)
        handler_id = spinbtn.connect(
            "value-changed", self._on_value_changed_cb, property_name)
        disable_scroll(spinbtn)
        self.spin_buttons[property_name] = spinbtn
        self.spin_buttons_handler_ids[property_name] = handler_id

    def _on_value_changed_cb(self, spinbtn, prop):
        if not self.source:
            return

        value = spinbtn.get_value()

        res, cvalue = self.__get_source_property(prop)
        if not res:
            return

        if value != cvalue:
            with self.app.action_log.started("Transformation property change",
                                             finalizing_action=CommitTimelineFinalizingAction(self._project.pipeline),
                                             toplevel=True):
                self.__set_prop(prop, value)
            self.app.gui.editor.viewer.overlay_stack.update(self.source)

    def set_source(self, source):
        self.debug("Setting source to %s", source)

        if self.source:
            self.source.disconnect_by_func(self.__source_property_changed_cb)
            disconnect_all_by_func(self.source, self._control_bindings_changed)

        self.source = source

        if self.source:
            self.__update_control_bindings()
            for prop in self.spin_buttons:
                self.__update_spin_btn(prop)
            self.__update_keyframes_ui()
            self.source.connect("deep-notify", self.__source_property_changed_cb)
            self.source.connect("control-binding-added", self._control_bindings_changed)
            self.source.connect("control-binding-removed", self._control_bindings_changed)

        self.set_visible(bool(self.source))
