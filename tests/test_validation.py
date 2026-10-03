import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

import auto_location_modifier as app


def config(**overrides):
    return {'mumu_path': 'MuMuManager.exe', 'interval': 1, 'max_distance': 5,
            'vm_indexes': 0, 'loop': False, 'location': [],
            'path_points': [[0, 0], [0.0001, 0]], **overrides}


class ValidationTests(unittest.TestCase):
    def test_valid_configuration(self):
        app.validate_config(config())
        app.validate_config(config(vm_indexes='all'))

    def test_invalid_numbers(self):
        for key in ['interval', 'max_distance']:
            for value in [0, -1, float('nan'), float('inf'), True, '5']:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    app.validate_config(config(**{key: value}))

    def test_coordinates_and_shape(self):
        for points in [[[181, 0]], [[0, 91]], [[True, 0]], [[0]], [[0, float('inf')]], 'invalid']:
            with self.subTest(points=points), self.assertRaises(ValueError):
                app.validate_points(points)

    def test_loop_and_indexes(self):
        for overrides in [{'loop': 'false'}, {'vm_indexes': -1}, {'vm_indexes': True}, {'vm_indexes': 'oops'}, {'location': 'bad'}]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                app.validate_config(config(**overrides))

    def test_empty_template_validates_but_cannot_start(self):
        app.validate_config(config(path_points=[]))
        with self.assertRaises(ValueError):
            app.validate_config(config(path_points=[]), require_path=True)

    def test_interpolation_endpoints_and_spacing(self):
        points = app.interpolate_path([[0, 0], [0.0002, 0]], max_distance=5, loop=False)
        self.assertEqual(tuple(points[0]), (0, 0))
        self.assertEqual(tuple(points[-1]), (0.0002, 0))
        for first, second in zip(points, points[1:]):
            self.assertLessEqual(app.euclidean_distance(*first, *second) * 111000, 5)

    def test_loop_does_not_duplicate_start_with_json_list_coordinates(self):
        points = app.interpolate_path([[0, 0], [0.0002, 0]], max_distance=5, loop=True)
        self.assertEqual(points.count((0, 0)), 1)

    def test_partial_existing_config_keeps_default_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'partial.cfg'
            target.write_text('{"interval": 2}', encoding='utf-8')
            with patch.object(app, 'resource_path', return_value=directory), contextlib.redirect_stdout(io.StringIO()):
                loaded, filename = app.load_config()
            self.assertEqual(loaded['interval'], 2)
            self.assertTrue(loaded['mumu_path'].endswith('MuMuManager.exe'))
            self.assertEqual(filename, str(target))

    def test_zero_spacing_and_excessive_point_count_are_rejected(self):
        for distance in [0, 0.00001]:
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                app.interpolate_path([[0, 0], [1, 1]], max_distance=distance)

    def test_failed_atomic_save_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'config.cfg'
            target.write_text('original', encoding='utf-8')
            with patch.object(app.os, 'replace', side_effect=OSError('disk error')), contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(app.save_config(config(), str(target)))
            self.assertEqual(target.read_text(), 'original')
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_successful_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            target = Path(directory) / 'config.cfg'
            self.assertTrue(app.save_config(config(), str(target)))
            self.assertEqual(json.loads(target.read_text()), config())

    def test_manager_timeout_is_reported_and_bounded(self):
        with patch.object(app.subprocess, 'run', side_effect=subprocess.TimeoutExpired('manager', 15)) as run:
            with self.assertRaises(RuntimeError):
                app.change_location(0, 0, 0, 'manager')
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_offline_check_never_calls_manager_or_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'config.cfg'
            target.write_text(json.dumps(config()), encoding='utf-8')
            with patch.object(app.subprocess, 'run') as run, patch.object(app, 'save_config') as save, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.cli(['--check-config', str(target)]), 0)
            run.assert_not_called()
            save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
