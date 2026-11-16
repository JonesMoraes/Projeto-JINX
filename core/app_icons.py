"""User-supplied JINX icon catalog and local shortcut updates. No Qt imports."""
from pathlib import Path
import sys
from memory import config_manager as config

ROOT = Path(__file__).resolve().parents[1]
CATALOG = (
    ('01_jinx_perfil_circuitos', 'Perfil com circuitos'),
    ('02_jinx_headset_sorrindo', 'Headset sorrindo'),
    ('03_jinx_oculos_vr', 'Óculos de realidade virtual'),
    ('04_jinx_mira_holografica', 'Mira holográfica'),
    ('05_jinx_glitch_cibernetico', 'Glitch cibernético'),
    ('06_jinx_perfil_codigo_azul', 'Código azul'),
    ('07_jinx_olho_bionico', 'Olho biônico'),
    ('08_jinx_headset_raios', 'Headset com raios'),
    ('09_jinx_capuz_engrenagens', 'Capuz e engrenagens'),
    ('10_jinx_codigo_binario', 'Código binário'),
)
DEFAULT_ICON = '02_jinx_headset_sorrindo'


def icon_path(icon_id):
    if icon_id not in {key for key, _ in CATALOG}:
        raise ValueError('Escolha um dos ícones da galeria.')
    directory = ROOT / 'assets' / 'app_icons'
    path = directory / (icon_id + '.ico')
    if directory.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Caminho de ícone inválido.')
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('O arquivo do ícone não está disponível.')
    with path.open('rb') as stream:
        if stream.read(4) != b'\x00\x00\x01\x00':
            raise ValueError('O arquivo não é um ícone Windows válido.')
    return path


def available_icons():
    rows = []
    for key, label in CATALOG:
        try:
            rows.append({'id': key, 'label': label, 'path': icon_path(key)})
        except ValueError:
            continue
    return rows


def selected_id():
    value = config.load_api_keys().get('app_icon', DEFAULT_ICON)
    if not isinstance(value, str):
        value = DEFAULT_ICON
    try:
        icon_path(value)
        return value
    except ValueError:
        return DEFAULT_ICON


def selected_path():
    try:
        return icon_path(selected_id())
    except ValueError:
        # Keep legacy installations usable if the optional catalog is absent.
        return config.CONFIG_DIR / 'jinx.ico'


def select(icon_id):
    path = icon_path(icon_id)
    config.update_config(app_icon=icon_id)
    if config.load_api_keys().get('app_icon') != icon_id:
        raise OSError('Não foi possível confirmar a gravação do ícone.')
    return path


def update_shortcuts(desktop, *, shell=None):
    """Change icons only on existing JINX links for this installation.

    Target, launch arguments and working directory are never changed here.
    Injectable shell supports isolated tests without modifying the real desktop.
    """
    if sys.platform != 'win32' and shell is None:
        return {'updated': [], 'failed': []}
    if shell is None:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            from win32com.client import Dispatch
            shell = Dispatch('WScript.Shell')
            return update_shortcuts(desktop, shell=shell)
        finally:
            shell = None
            pythoncom.CoUninitialize()
    icon = str(selected_path().resolve()) + ',0'
    result = {'updated': [], 'failed': []}
    for link in sorted(Path(desktop).glob('*.lnk')):
        try:
            shortcut = shell.CreateShortcut(str(link))
            target = Path(shortcut.TargetPath).resolve()
            own = target == ROOT.resolve() or (
                target.is_relative_to(ROOT.resolve()) and
                target.name.lower() in ('pythonw.exe', 'python.exe', 'main.py', 'launch_jinx.pyw', 'jinx.exe'))
            if not own:
                continue
            shortcut.IconLocation = icon
            shortcut.Save()
            saved = shell.CreateShortcut(str(link))
            if saved.IconLocation.casefold() != icon.casefold():
                raise OSError('Shortcut icon write was not verified')
            result['updated'].append(link.name)
        except Exception:
            result['failed'].append(link.name)
    if result['updated'] and sys.platform == 'win32':
        try:
            import ctypes
            # Notify Explorer that icon associations changed; no cache deletion.
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass
    return result
