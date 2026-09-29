"""Choose and snapshot a local register independently of the matching engine."""
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from src.filtering.filter_engine import DEFAULT_SETTINGS_PATH
from src.ingestion.contract_reader import read_contract_registry
from src.models.supplier import ContractRegistry
from src.supplier_matching.settings import load_matching_settings, snapshot_date

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RegistrySource:
    kind: str
    name: str | None
    content: bytes | None
    snapshot_date: date | None
    issue: str | None = None
    format_suffix: str = '.xlsx'

    @property
    def sha256(self):
        return sha256(self.content).hexdigest() if self.content is not None else None


def default_registry_location(config):
    configured = config.get('default_registry_path')
    if not configured:
        return None, 'Ej konfigurerat'
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path, config.get('default_registry_name') or path.name


def resolve_registry_source(*, settings_path=DEFAULT_SETTINGS_PATH, mode='default',
                            uploaded_content=None, uploaded_name=None, path=None,
                            registry_snapshot_date=None):
    if mode not in ('default', 'uploaded', 'disabled'):
        raise ValueError('Unknown register source mode')
    if mode == 'disabled':
        return RegistrySource('disabled', None, None, None, 'Avtalsregistret är avaktiverat.')
    config = load_matching_settings(settings_path)
    supplied_date = registry_snapshot_date if registry_snapshot_date is not None else config.get('registry_snapshot_date')
    snapshot = snapshot_date(supplied_date) if supplied_date is not None else None
    if uploaded_content is not None:
        return RegistrySource('uploaded', uploaded_name or 'Uppladdat register.xlsx',
                              bytes(uploaded_content), snapshot,
                              format_suffix=Path(uploaded_name or 'register.xlsx').suffix.lower())
    if mode == 'uploaded' and path is None:
        return RegistrySource('uploaded', None, None, snapshot, 'Inget eget register har laddats upp.')
    kind = 'supplied' if path is not None else 'default'
    selected, name = ((Path(path).expanduser(), Path(path).name) if path is not None
                      else default_registry_location(config))
    if selected is None:
        return RegistrySource(kind, None, None, snapshot, 'Ingen standardregisterfil är konfigurerad.')
    try:
        content = selected.read_bytes()
    except OSError:
        return RegistrySource(kind, name, None, snapshot,
                              f'Registerfilen {name} saknas eller kan inte läsas.')
    return RegistrySource(kind, name, content, snapshot, format_suffix=selected.suffix.lower())


def load_contract_source(source, *, config):
    if source.content is None:
        registry = ContractRegistry(issues=(source.issue or 'Register saknas.',),
                                    snapshot_date=source.snapshot_date)
    else:
        # Source names are labels only, never paths for uploaded working copies.
        suffix = source.format_suffix
        with TemporaryDirectory(prefix='contract-register-') as directory:
            path = Path(directory) / ('register' + suffix)
            path.write_bytes(source.content)
            registry = read_contract_registry(path, config=config, snapshot=source.snapshot_date)
    registry.source_name = source.name
    registry.source_kind = source.kind
    registry.source_sha256 = source.sha256
    return registry
