# =============================================================================
# Modified for arena bootstrap: dotenv is optional (no .env file in sandbox)
# Original code:
#   from dotenv import load_dotenv
#   load_dotenv(Path(__file__).resolve().parent / '.env')
# =============================================================================
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

# Le profil sandbox est conservé à la racine du monorepo (hors application
# backend) ; exposer cette racine permet `--settings=arena.settings_sandbox`
# depuis le répertoire backend sans modifier le PYTHONPATH à la main.
_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if (_REPOSITORY_ROOT / 'arena').is_dir() and str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass  # dotenv not available in sandbox — no .env file needed


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
