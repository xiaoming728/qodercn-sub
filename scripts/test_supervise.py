import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('supervise', Path(__file__).with_name('supervise.py'))
supervise = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervise)


class LaunchTests(unittest.TestCase):
    def test_external_materials_do_not_require_add_dir_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cwd = root / 'workspace'
            cwd.mkdir()
            task = root / "task files' 中文" / 'task.md'
            task.parent.mkdir()
            task.write_text('read-only smoke task')
            run = root / 'run files'
            config = root / '.qoder-cn/settings.json'
            config.parent.mkdir()
            original = json.dumps({'permissions': {'trustDirectories': [str(cwd)]}})
            config.write_text(original)
            commands = []

            def place(script, *args):
                commands.append(shlex.split(args[1]))
                return 'test-terminal'

            with patch.object(Path, 'home', return_value=root), \
                    patch.object(supervise, 'STATE', root / 'state'), \
                    patch.object(supervise.shutil, 'which', return_value='/bin/qoderclicn'), \
                    patch.object(supervise, 'osa', side_effect=place), \
                    contextlib.redirect_stdout(io.StringIO()):
                supervise.prepare(argparse.Namespace(cwd=str(cwd), task=str(task), run_dir=str(run)))
                supervise.launch(argparse.Namespace(run_dir=str(run), model='dfmodel', group='test'))

            argv = commands[0]
            self.assertNotIn('--add-dir', argv, 'Qoder v1.1.83 prompts even for trusted --add-dir paths')
            settings = json.loads(argv[argv.index('--settings') + 1])
            self.assertEqual(set(settings['permissions']['additionalDirectories']), {
                str(run), str(task.parent), str(Path(__file__).resolve().parents[1]),
            })
            self.assertEqual(argv[argv.index('-i') + 1], f'完整读取并执行 {run / "worker.md"}')
            self.assertEqual(argv[argv.index('--permission-mode') + 1], 'bypass_permissions')
            self.assertEqual(config.read_text(), original)

    def test_launch_ignores_closed_terminal_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cwd = root / 'workspace'
            cwd.mkdir()
            task = root / 'task.md'
            task.write_text('task')
            run = root / 'run'
            config = root / '.qoder-cn/settings.json'
            config.parent.mkdir()
            config.write_text(json.dumps({'permissions': {'trustDirectories': [str(cwd)]}}))
            placements = []

            def osa(script, *args):
                if script == supervise.ALIVE:
                    return 'live-terminal'
                if script == supervise.PLACE:
                    placements.append(args)
                    return 'new-terminal'
                raise AssertionError(f'unexpected script: {script}')

            with patch.object(Path, 'home', return_value=root), \
                    patch.object(supervise, 'STATE', root / 'state'), \
                    patch.object(supervise.shutil, 'which', return_value='/bin/qoderclicn'), \
                    patch.object(supervise, 'osa', side_effect=osa), \
                    contextlib.redirect_stdout(io.StringIO()):
                supervise.prepare(argparse.Namespace(cwd=str(cwd), task=str(task), run_dir=str(run)))
                state = root / 'state' / 'test.json'
                state.parent.mkdir()
                state.write_text(json.dumps(['dead-terminal', 'live-terminal']))
                supervise.launch(argparse.Namespace(run_dir=str(run), model='dfmodel', group='test'))

            self.assertEqual(placements[0][2], 'right')
            self.assertEqual(placements[0][3], 'live-terminal')
            self.assertEqual(json.loads(state.read_text()), ['live-terminal', 'new-terminal'])


class WaitTests(unittest.TestCase):
    task_id = 'wait-task'

    def make_run(self, root, status='READY', terminal_id='terminal-1', final=True):
        run = root / 'run'
        run.mkdir()
        (run / 'manifest.json').write_text(json.dumps(
            {'task_id': self.task_id, 'cwd': str(root), 'task': str(root / 'task.md')}))
        if final:
            (run / 'final.json').write_text(json.dumps({
                'task_id': self.task_id, 'status': status, 'summary': 'done',
                'checks': ['x'], 'refs': {}, 'blocked': [], 'report_path': '/tmp/report.md'}))
        if terminal_id is not None:
            (run / 'terminal_id').write_text(terminal_id)
        return run

    def run_wait(self, run, alive=(), close_error=None, timeout=1):
        calls = []

        def osa(script, *args):
            if script == supervise.ALIVE:
                calls.append(('alive',) + args)
                return '\n'.join(a for a in args if a in alive)
            if script == supervise.CLOSE:
                calls.append(('close',) + args)
                if close_error:
                    raise close_error
                return ''
            raise AssertionError(f'unexpected script: {script}')

        out, err = io.StringIO(), io.StringIO()
        with patch.object(supervise, 'osa', side_effect=osa), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = supervise.wait(argparse.Namespace(
                run_dir=str(run), timeout=timeout, pid=None, poll_interval=0.01))
        return code, json.loads(out.getvalue()), err.getvalue(), calls

    def test_ready_closes_exact_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve(), terminal_id=' terminal-1\n')
            code, result, err, calls = self.run_wait(run, alive=('terminal-1',))
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual([c for c in calls if c[0] == 'close'], [('close', 'terminal-1')])
        self.assertEqual(err, '')

    def test_non_ready_status_keeps_terminal(self):
        for status in ('BLOCKED', 'FAILED'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                run = self.make_run(Path(tmp).resolve(), status=status)
                code, result, _, calls = self.run_wait(run, alive=('terminal-1',))
            self.assertEqual(code, 0)
            self.assertEqual(result['status'], status)
            self.assertEqual([c for c in calls if c[0] == 'close'], [])

    def test_invalid_result_keeps_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve())
            final = json.loads((run / 'final.json').read_text())
            final['task_id'] = 'other-task'
            (run / 'final.json').write_text(json.dumps(final))
            code, result, _, calls = self.run_wait(run, alive=('terminal-1',))
        self.assertEqual(code, 2)
        self.assertEqual(result['monitor_status'], 'INVALID_RESULT')
        self.assertEqual(calls, [])

    def test_timeout_keeps_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve(), final=False)
            code, result, _, calls = self.run_wait(run, alive=('terminal-1',), timeout=0)
        self.assertEqual(code, 4)
        self.assertEqual(result['monitor_status'], 'TIMEOUT')
        self.assertEqual(calls, [])

    def test_missing_terminal_id_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve(), terminal_id=None)
            code, result, err, calls = self.run_wait(run, alive=('terminal-1',))
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(calls, [])
        self.assertEqual(err, '')

    def test_already_closed_terminal_is_not_closed_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve())
            code, result, err, calls = self.run_wait(run, alive=())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual([c for c in calls if c[0] == 'close'], [])
        self.assertEqual(err, '')

    def test_close_failure_reports_warning_and_keeps_result(self):
        error = subprocess.CalledProcessError(1, 'osascript', '', 'close failed')
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve())
            code, result, err, calls = self.run_wait(run, alive=('terminal-1',), close_error=error)
        self.assertEqual(code, 0)
        self.assertEqual(set(result), {'task_id', 'status', 'summary', 'checks', 'refs', 'blocked', 'report_path'})
        self.assertEqual(result['status'], 'READY')
        self.assertIn('terminal-1', err)
        self.assertIn('close failed', err)
        self.assertEqual([c for c in calls if c[0] == 'close'], [('close', 'terminal-1')])

    def test_repeated_wait_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp).resolve())
            first = self.run_wait(run, alive=('terminal-1',))
            second = self.run_wait(run, alive=())
        self.assertEqual(first[0], 0)
        self.assertEqual(second[0], 0)
        self.assertEqual(first[1], second[1])
        self.assertEqual([c for c in first[3] if c[0] == 'close'], [('close', 'terminal-1')])
        self.assertEqual([c for c in second[3] if c[0] == 'close'], [])


if __name__ == '__main__':
    unittest.main()
