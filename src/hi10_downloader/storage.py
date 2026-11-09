"""Crash-resistant private JSON storage with last-known-good recovery."""
import json
import logging
import os
from pathlib import Path
import tempfile

log = logging.getLogger(__name__)


def _unlink(path):
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _replace(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_json(path, data):
    path = Path(path)
    content = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode()
    if path.exists():
        previous = path.read_bytes()
        try:
            json.loads(previous)
        except (ValueError, UnicodeError):
            pass  # Never overwrite a good backup with corrupt state.
        else:
            _replace(path.with_name(path.name + '.bak'), previous)
    _replace(path, content)


def load_json(path, validate=None):
    path = Path(path)
    def decode(content):
        data = json.loads(content)
        if validate and not validate(data):
            raise ValueError('Invalid state structure')
        return data
    try:
        return decode(path.read_bytes())
    except (ValueError, UnicodeError):
        backup = path.with_name(path.name + '.bak')
        try:
            content = backup.read_bytes()
            data = decode(content)
        except (OSError, ValueError, UnicodeError):
            raise ValueError(f'{path.name} is invalid and has no valid backup. Restore it from an appdata backup; the original file was retained.') from None
        # Retain the damaged original for investigation; never log its contents.
        _replace(path.with_name(path.name + '.corrupt'), path.read_bytes())
        _replace(path, content)
        log.warning('Recovered %s from its last-known-good backup', path.name)
        return data

# Recoverable roll-forward transactions for state changes spanning several files.
# A journal is private and is replayed before any state is loaded on next startup.
from contextvars import ContextVar
from contextlib import contextmanager

_transaction = ContextVar('state_transaction', default=None)
_single_save = save_json


def save_json(path, data):
    staged = _transaction.get()
    if staged is None:
        return _single_save(path, data)
    staged[str(Path(path).absolute())] = {'op': 'write', 'data': data}


def recover_transaction(config, output):
    journal = Path(config) / 'pending-transaction.json'
    if not journal.exists():
        return
    records = load_json(journal, lambda d: isinstance(d, dict) and d.get('version') in {1, 2} and isinstance(d.get('writes'), dict))
    roots = [Path(config).resolve(), Path(output).resolve()]
    for name, value in records['writes'].items():
        if not isinstance(name, str) or (records['version'] == 2 and (not isinstance(value, dict) or value.get('op') not in {'write', 'delete'} or (value.get('op') == 'write' and 'data' not in value))):
            raise ValueError('Invalid transaction operation. Restore appdata from backup.')
        path = Path(name).resolve()
        if not any(path.is_relative_to(root) for root in roots) or path == journal.resolve():
            raise ValueError('State transaction contains an invalid destination. Restore appdata from backup.')
    for name, value in records['writes'].items():
        if records['version'] == 1:
            _single_save(Path(name), value)
        elif not isinstance(value, dict) or value.get('op') not in {'write', 'delete'}:
            raise ValueError('Invalid transaction operation. Restore appdata from backup.')
        elif value['op'] == 'delete':
            _unlink(name)
        else:
            _single_save(Path(name), value['data'])
    _unlink(journal.with_name(journal.name + '.bak'))
    _unlink(journal)


@contextmanager
def transaction(config, output):
    if _transaction.get() is not None:
        yield
        return
    writes = {}
    token = _transaction.set(writes)
    try:
        yield
    except Exception:
        raise
    else:
        if writes:
            journal = Path(config) / 'pending-transaction.json'
            _single_save(journal, {'version': 2, 'writes': writes})
            recover_transaction(config, output)
    finally:
        _transaction.reset(token)


def delete_file(path):
    staged = _transaction.get()
    if staged is None:
        _unlink(path)
    else:
        staged[str(Path(path).absolute())] = {'op': 'delete'}
