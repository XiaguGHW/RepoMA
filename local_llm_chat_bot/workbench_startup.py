"""Standard-library bootstrap; help and dependency recovery work before app imports."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile


APP_DIRECTORY = Path(__file__).resolve().parent
HOST = '127.0.0.1'
RECOVERY = {
    'startup.env_missing': 'Configuration file not found: {path}. Create it or restart with --env-file "PATH". Keep credentials out of command arguments.',
    'startup.env_unreadable': 'Cannot read configuration: {path}. Check file permissions and UTF-8 encoding, then retry.',
    'startup.key_missing': 'No Farm key was loaded from {path} or the process environment. Set BOSCH_FARM_SUBSCRIPTION_KEY (or BOSCH_FARM_API_KEY) in that file, then retry.',
    'startup.state_unwritable': 'Cannot write application state in {path}. Check permissions, free disk space and file locks, or move the complete program folder to a writable location and restart. Do not use the BG source folder.',
    'startup.state_fixed': 'The GUI stores state in {path}. Remove state_dir from the request; move the complete program folder if that location is not writable.',
    'startup.port_busy': 'Cannot listen on 127.0.0.1:{port}. If Workbench is already running, open http://127.0.0.1:{port}. Otherwise choose another port with --port 8877. Keep the existing instance running unless you intend to close it.',
    'startup.server_failed': 'Workbench could not start on 127.0.0.1:{port}. Check the server error above, reuse an existing Workbench instance, or restart with another --port.',
    'startup.endpoint_invalid': 'BOSCH_FARM_BASE_URL in {path} or the process environment is invalid. Use an HTTP(S) URL without embedded credentials, then retry.',
}


class StartupError(RuntimeError):
    def __init__(self, code: str, **params: object):
        self.code = code
        self.params = params
        super().__init__(RECOVERY[code].format(**params))


@dataclass(frozen=True)
class StartupConfig:
    env_file: Path = field(default_factory=lambda: APP_DIRECTORY / '.env')
    env_explicit: bool = False
    port: int = 8765


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('port must be an integer from 1 to 65535') from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('port must be an integer from 1 to 65535')
    return port


def parse_options(argv: Sequence[str] | None = None) -> StartupConfig:
    parser = argparse.ArgumentParser(description='Local Bosch Workbench (127.0.0.1 only). Python 3.10+ is required.')
    parser.add_argument('--env-file', metavar='PATH', help='UTF-8 Farm configuration; default: .env beside the program. Relative paths use the launch directory.')
    parser.add_argument('--port', type=port_number, default=8765, help='local TCP port, default: 8765')
    args = parser.parse_args(argv)
    if args.env_file is not None and not args.env_file.strip():
        parser.error('--env-file must not be empty')
    try:
        path = Path(args.env_file).expanduser().resolve() if args.env_file is not None else APP_DIRECTORY / '.env'
    except (OSError, ValueError):
        parser.error('cannot resolve --env-file; use a valid file path')
    return StartupConfig(env_file=path, env_explicit=args.env_file is not None, port=args.port)


def install_command() -> str:
    args = [sys.executable, '-m', 'pip', 'install', '-r', str(APP_DIRECTORY / 'requirements.txt')]
    return '& ' + subprocess.list2cmdline(args) if os.name == 'nt' else shlex.join(args)


def check_dependencies() -> None:
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10 or newer is required. Install and select that interpreter, then run:\n'
                           'python -m pip install -r "' + str(APP_DIRECTORY / 'requirements.txt') + '"')
    packages = {'fastapi': 'fastapi', 'uvicorn': 'uvicorn', 'pydantic': 'pydantic', 'dotenv': 'python-dotenv',
                'requests': 'requests', 'openai': 'openai', 'fitz': 'PyMuPDF', 'PIL': 'Pillow',
                'pytesseract': 'pytesseract', 'openpyxl': 'openpyxl', 'docx': 'python-docx'}
    missing = [package for module, package in packages.items() if importlib.util.find_spec(module) is None]
    if missing:
        raise RuntimeError('Missing Python packages: ' + ', '.join(missing) + '\nInstall into this Python environment:\n' + install_command())
    broken = []
    for module, package in packages.items():
        try:
            importlib.import_module(module)
        except Exception as exc:
            broken.append(f'{package} ({type(exc).__name__})')
    if broken:
        raise RuntimeError('Cannot load Python packages: ' + ', '.join(broken) +
                           '\nRepair this Python environment:\n' + install_command())


def bootstrap() -> StartupConfig:
    config = parse_options()  # Unknown options/help must work even without dependencies.
    try:
        check_dependencies()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    return config


class FarmEnvironment:
    """Track only dotenv-added values; external process variables keep precedence."""
    def __init__(self) -> None:
        self._loaded: dict[str, str] = {}

    @contextmanager
    def use(self, path: Path, loader: Callable[..., object], *, explicit: bool = False,
            commit: bool = True) -> Iterator[str]:
        # The app holds its shared lock while this context is active. A rejected
        # setup/probe cannot change the endpoint/key of an existing session.
        snapshot = dict(os.environ)
        previous = self._loaded.copy()
        succeeded = False
        try:
            for name, value in previous.items():
                if os.environ.get(name) == value:
                    os.environ.pop(name, None)
            before = dict(os.environ)
            try:
                if explicit and not path.is_file():
                    raise StartupError('startup.env_missing', path=path)
                if path.exists() and not path.is_file():
                    raise StartupError('startup.env_unreadable', path=path)
                loader(path, override=False, encoding='utf-8-sig')
            except (OSError, UnicodeError):
                raise StartupError('startup.env_unreadable', path=path) from None
            key = os.getenv('BOSCH_FARM_SUBSCRIPTION_KEY') or os.getenv('BOSCH_FARM_API_KEY')
            if not key or not key.strip():
                raise StartupError('startup.key_missing', path=path)
            yield key
            if commit:
                self._loaded = {name: value for name, value in os.environ.items() if name not in before}
                succeeded = True
        finally:
            if not succeeded:
                os.environ.clear()
                os.environ.update(snapshot)
                self._loaded = previous


def check_state_directory(path: Path) -> None:
    probe: Path | None = None
    replaced: Path | None = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix='.write-check-', delete=False) as handle:
            probe = Path(handle.name)
            handle.write(b'workbench')
            handle.flush()
        replaced = probe.with_suffix('.replace')
        os.replace(probe, replaced)
        replaced.unlink()
    except OSError:
        raise StartupError('startup.state_unwritable', path=path) from None
    finally:
        for temporary in (probe, replaced):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def check_port(port: int) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((HOST, port))
    except OSError:
        raise StartupError('startup.port_busy', port=port) from None
