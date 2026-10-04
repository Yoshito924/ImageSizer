import threading
import unittest
from unittest.mock import MagicMock, patch

from gui import ImageProcessorApp


class QueueTests(unittest.TestCase):
    def test_add_during_batch_survives_clear_and_selected_delete(self):
        for action in ("clear_all_files", "remove_selected_files"):
            with self.subTest(action=action):
                app = ImageProcessorApp.__new__(ImageProcessorApp)
                items = ["A.png", "B.png"]
                box = app.file_listbox = MagicMock()
                box.get.side_effect = lambda *args: tuple(items)
                box.size.side_effect = lambda: len(items)
                box.insert.side_effect = lambda where, item: items.append(item)
                box.delete.side_effect = lambda index, *args: items.pop(index)
                box.curselection.return_value = (0, 1)
                app.master = MagicMock()
                app.output_text = MagicMock()
                app.progress = {}
                app.is_processing = False
                app._shutdown_event = threading.Event()
                app._refresh_ui_state = MagicMock()
                values = dict(size_type_var="none", operation_var="auto", crop_var="none",
                              format_var="png", output_dest_var="original", preset_var="カスタム",
                              warn_on_overwrite_var=False)
                for name in ("include_crop_type", "include_size_ratio", "include_timestamp",
                             "include_sequential", "include_preset_name"):
                    values[name] = False
                for name, value in values.items():
                    var = MagicMock()
                    var.get.return_value = value
                    setattr(app, name, var)
                calls = []
                def process(file, *args, **kwargs):
                    calls.append(file)
                    return None, 1, "done"
                with patch("gui.threading.Thread") as worker, patch("gui.process_image", side_effect=process):
                    app.process_images()
                    self.assertTrue(app.is_processing)
                    getattr(app, action)()
                    self.assertEqual(items, ["A.png", "B.png"])
                    app.add_files(["C.png"])
                    worker.call_args.kwargs["target"]()
                    app.master.after.call_args_list[0].args[1]()
                    self.assertEqual(items, ["C.png"])
                    self.assertFalse(app.is_processing)
                    app.master.after.call_args.args[1]()
                    worker.call_args.kwargs["target"]()
                    app.master.after.call_args.args[1]()
                self.assertEqual(calls, ["A.png", "B.png", "C.png"])
                self.assertEqual(items, [])

    def test_closing_keeps_parent_shells_and_cleans_registered_children(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app._is_closing = False
        app.is_processing = False
        app.master = MagicMock()
        app.save_settings = MagicMock()
        app._shutdown_event = threading.Event()
        app._worker_thread = None
        app._terminate_child_processes = MagicMock()
        with patch("gui.subprocess.run") as run:
            app.on_closing()
        run.assert_not_called()
        app._terminate_child_processes.assert_called_once_with()
        app.master.destroy.assert_called_once_with()

    def test_edit_buttons_follow_processing_state(self):
        app = ImageProcessorApp.__new__(ImageProcessorApp)
        app.file_remove_button = MagicMock()
        app.file_clear_button = MagicMock()
        for name in ("_update_file_summary", "_update_output_status", "_update_preset_status"):
            setattr(app, name, MagicMock())
        for processing, state in ((True, "disabled"), (False, "normal")):
            app.is_processing = processing
            app._refresh_ui_state()
            app.file_remove_button.configure.assert_called_with(state=state)
            app.file_clear_button.configure.assert_called_with(state=state)
