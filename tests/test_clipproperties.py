# -*- coding: utf-8 -*-
# Pitivi video editor
# Copyright (c) 2014, Alex Băluț <alexandru.balut@gmail.com>
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
"""Tests for the pitivi.clipproperties module."""
# pylint: disable=protected-access,no-self-use,import-outside-toplevel,no-member
from unittest import mock

from gi.repository import GES

from tests import common


class TransformationPropertiesTest(common.TestCase):
    """Tests for the TransformationProperties widget."""

    @common.setup_timeline
    @common.setup_clipproperties
    def test_spin_buttons_read(self):
        """Checks the spin buttons update when the source properties change."""
        # Create transformation box
        transformation_box = self.transformation_box
        timeline = transformation_box.app.gui.editor.timeline_ui.timeline
        spin_buttons = transformation_box.spin_buttons

        # Add a clip and select it
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])

        # Check that spin buttons display the correct values by default
        source = transformation_box.source
        self.assertIsNotNone(source)
        for prop in ["posx", "posy", "width", "height"]:
            self.assertIn(prop, spin_buttons)
            ret, source_value = source.get_child_property(prop)
            self.assertTrue(ret)
            spin_btn_value = spin_buttons[prop].get_value_as_int()
            self.assertEqual(spin_btn_value, source_value)

        # Change the source properties and check the spin buttons update
        # correctly.
        new_values = {"posx": 20, "posy": -50, "width": 70, "height": 450}
        for prop, new_val in new_values.items():
            self.assertTrue(source.set_child_property(prop, new_val))
            spin_btn_value = spin_buttons[prop].get_value_as_int()
            self.assertEqual(new_val, spin_btn_value)

    @common.setup_timeline
    @common.setup_clipproperties
    def test_spin_buttons_write(self):
        """Checks the spin buttons changing updates the source properties."""
        # Create transformation box
        timeline = self.transformation_box.app.gui.editor.timeline_ui.timeline
        spin_buttons = self.transformation_box.spin_buttons

        # Add a clip and select it
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])
        source = self.transformation_box.source
        self.assertIsNotNone(source)

        # Get current spin buttons values
        current_spin_values = {}
        for prop in ["posx", "posy", "width", "height"]:
            current_spin_values[prop] = spin_buttons[prop].get_value_as_int()

        changes = [
            ("posx", -300), ("posy", 450), ("width", 1), ("height", 320),
            ("posx", 230), ("posx", 520), ("posy", -10), ("posy", -1000),
            ("width", 600), ("width", 1000), ("height", 1), ("height", 1000)
        ]

        # Change the spin buttons values and check the source properties are
        # updated correctly.
        for prop, new_value in changes:
            spin_buttons[prop].set_value(new_value)
            current_spin_values[prop] = new_value
            for source_prop in ["posx", "posy", "width", "height"]:
                ret, source_value = source.get_child_property(source_prop)
                self.assertTrue(ret)
                self.assertEqual(current_spin_values[source_prop], source_value)

    @common.setup_timeline
    @common.setup_clipproperties
    def test_spin_buttons_source_change(self):
        """Checks the spin buttons update when the selected clip changes."""
        # Create transformation box
        timeline = self.transformation_box.app.gui.editor.timeline_ui.timeline
        spin_buttons = self.transformation_box.spin_buttons

        # Add two clips and select the first one
        clips = self.add_clips_simple(timeline, 2)
        timeline.selection.select([clips[0]])
        source = self.transformation_box.source
        self.assertIsNotNone(source)

        # Change the spin buttons values
        new_values = {"posx": 45, "posy": 10, "width": 450, "height": 25}
        for prop, new_val in new_values.items():
            spin_buttons[prop].set_value(new_val)

        # Select the second clip and check the spin buttons values update
        # correctly
        timeline.selection.select([clips[1]])
        source = self.transformation_box.source
        self.assertIsNotNone(source)
        for prop in ["posx", "posy", "width", "height"]:
            ret, source_value = source.get_child_property(prop)
            self.assertTrue(ret)
            self.assertEqual(spin_buttons[prop].get_value_as_int(), source_value)

        # Select the first clip again and check spin buttons values
        timeline.selection.select([clips[0]])
        for prop in ["posx", "posy", "width", "height"]:
            self.assertEqual(spin_buttons[prop].get_value_as_int(), new_values[prop])

    @common.setup_timeline
    @common.setup_clipproperties
    def test_keyframes_activate(self):
        """Checks transformation properties keyframes activation."""
        # Create transformation box
        timeline = self.transformation_box.app.gui.editor.timeline_ui.timeline

        # Add a clip and select it
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])
        source = self.transformation_box.source
        self.assertIsNotNone(source)
        inpoint = source.props.in_point
        duration = source.props.duration

        # Check keyframes are deactivated by default
        for prop in ["posx", "posy", "width", "height"]:
            self.assertIsNone(source.get_control_binding(prop))

        # Get current source properties
        initial_values = {}
        for prop in ["posx", "posy", "width", "height"]:
            ret, value = source.get_child_property(prop)
            self.assertTrue(ret)
            initial_values[prop] = value

        # Activate keyframes and check the default keyframes are created
        self.transformation_box._activate_keyframes_btn.set_active(True)
        for prop in ["posx", "posy", "width", "height"]:
            control_binding = source.get_control_binding(prop)
            self.assertIsNotNone(control_binding)
            control_source = control_binding.props.control_source
            keyframes = [(item.timestamp, item.value) for item in control_source.get_all()]
            self.assertEqual(keyframes, [(inpoint, initial_values[prop]),
                                         (inpoint + duration, initial_values[prop])])

    @common.setup_timeline
    @common.setup_clipproperties
    def test_keyframes_add(self):
        """Checks keyframe creation."""
        # Create transformation box
        timeline = self.transformation_box.app.gui.editor.timeline_ui.timeline
        pipeline = timeline._project.pipeline
        spin_buttons = self.transformation_box.spin_buttons

        # Add a clip and select it
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])
        source = self.transformation_box.source
        self.assertIsNotNone(source)
        start = source.props.start
        inpoint = source.props.in_point
        duration = source.props.duration

        # Activate keyframes
        self.transformation_box._activate_keyframes_btn.set_active(True)

        # Add some more keyframes
        offsets = [1, int(duration / 2), duration - 1]
        for prop in ["posx", "posy", "width", "height"]:
            for index, offset in enumerate(offsets):
                timestamp, value = inpoint + offset, offset * 10
                with mock.patch.object(pipeline, "get_position") as get_position:
                    get_position.return_value = start + offset
                    spin_buttons[prop].set_value(value)

                control_source = source.get_control_binding(prop).props.control_source
                keyframes = [(item.timestamp, item.value) for item in control_source.get_all()]
                self.assertEqual((timestamp, value), keyframes[index + 1])

    @common.setup_timeline
    @common.setup_clipproperties
    def test_keyframes_navigation(self):
        """Checks keyframe navigation."""
        # Create transformation box
        timeline = self.transformation_box.app.gui.editor.timeline_ui.timeline
        pipeline = timeline._project.pipeline

        # Add a clip and select it
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])
        source = self.transformation_box.source
        self.assertIsNotNone(source)
        start = source.props.start
        inpoint = source.props.in_point
        duration = source.props.duration

        # Activate keyframes and add some more keyframes
        self.transformation_box._activate_keyframes_btn.set_active(True)
        offsets = [1, int(duration / 2), duration - 1]
        for prop in ["posx", "posy", "width", "height"]:
            for offset in offsets:
                timestamp, value = inpoint + offset, offset * 10
                control_source = source.get_control_binding(prop).props.control_source
                control_source.set(timestamp, value)

        # Add edge keyframes in the offsets array
        offsets.insert(0, 0)
        offsets.append(duration)

        # Test keyframe navigation
        prev_index = 0
        next_index = 1
        for position in range(duration + 1):
            prev_keyframe_ts = offsets[prev_index] + inpoint
            next_keyframe_ts = offsets[next_index] + inpoint

            with mock.patch.object(pipeline, "get_position") as get_position:
                get_position.return_value = start + position
                with mock.patch.object(pipeline, "simple_seek") as simple_seek:
                    self.transformation_box._prev_keyframe_btn.clicked()
                    simple_seek.assert_called_with(prev_keyframe_ts)
                    self.transformation_box._next_keyframe_btn.clicked()
                    simple_seek.assert_called_with(next_keyframe_ts)

            if position + 1 == next_keyframe_ts and next_index + 1 < len(offsets):
                next_index += 1
            if position in offsets and position != 0:
                prev_index += 1

    @common.setup_timeline
    @common.setup_clipproperties
    def test_reset_to_default(self):
        """Checks "reset to default" button."""
        # Create transformation box
        timeline = self.transformation_box.app.gui.editor.timeline_ui.timeline

        # Add a clip and select it
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])
        source = self.transformation_box.source
        self.assertIsNotNone(source)

        # Change source properties
        new_values = {"posx": 20, "posy": -50, "width": 70, "height": 450}
        for prop, new_val in new_values.items():
            self.assertTrue(source.set_child_property(prop, new_val))

        # Activate keyframes
        self.transformation_box._activate_keyframes_btn.set_active(True)

        # Press "reset to default" button
        clear_button = self.transformation_box.builder.get_object("clear_button")
        clear_button.clicked()

        # Check that control bindings were erased and the properties were
        # reset to their default values
        for prop in ["posx", "posy", "width", "height"]:
            self.assertIsNone(source.get_control_binding(prop))
            ret, value = source.get_child_property(prop)
            self.assertTrue(ret)
            self.assertEqual(value, source.ui.default_position[prop])


class ClipPropertiesTest(common.TestCase):
    """Tests for the TitleProperties class."""

    def _get_title_source_child_props(self):
        clips = self.layer.get_clips()
        self.assertEqual(len(clips), 1, clips)
        self.assertIsInstance(clips[0], GES.TitleClip)
        source, = clips[0].get_children(False)
        return [source.get_child_property(p) for p in ("text",
                                                       "x-absolute", "y-absolute",
                                                       "valignment", "halignment",
                                                       "font-desc",
                                                       "color",
                                                       "foreground-color")]

    @common.setup_timeline
    @common.setup_clipproperties
    def test_create_title(self):
        """Exercise creating a title clip."""
        self.project.pipeline.get_position = mock.Mock(return_value=0)

        self.clipproperties.create_title_clip_cb(None)
        ps1 = self._get_title_source_child_props()

        self.action_log.undo()
        clips = self.layer.get_clips()
        self.assertEqual(len(clips), 0, clips)

        self.action_log.redo()
        ps2 = self._get_title_source_child_props()
        self.assertListEqual(ps1, ps2)

    @common.setup_timeline
    @common.setup_clipproperties
    def test_alignment_editor(self):
        """Exercise aligning a clip using the alignment editor."""
        self.project.pipeline.get_position = mock.Mock(return_value=0)

        timeline = self.timeline_container.timeline
        clip = self.add_clips_simple(timeline, 1)[0]
        timeline.selection.select([clip])
        source = self.transformation_box.source
        self.assertIsNotNone(source)

        height = source.get_child_property("height").value
        width = source.get_child_property("width").value

        self.assertEqual(source.get_child_property("posx").value, 0)
        self.assertEqual(source.get_child_property("posy").value, 0)

        alignment_editor = self.transformation_box.alignment_editor
        event = mock.MagicMock()
        event.x = 0
        event.y = 0
        alignment_editor._motion_notify_event_cb(None, event)
        alignment_editor._button_release_event_cb(None, None)

        self.assertEqual(source.get_child_property("posx").value, -width)
        self.assertEqual(source.get_child_property("posy").value, -height)

        self.action_log.undo()

        self.assertEqual(source.get_child_property("posx").value, 0)
        self.assertEqual(source.get_child_property("posy").value, 0)

        self.action_log.redo()

        self.assertEqual(source.get_child_property("posx").value, -width)
        self.assertEqual(source.get_child_property("posy").value, -height)
