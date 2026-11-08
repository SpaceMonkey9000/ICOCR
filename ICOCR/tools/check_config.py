"""Validate startup configuration without loading OCR models. Nonzero means fallback."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='print full configuration diagnostics')
    args = parser.parse_args(argv)
    from config_loader import configuration_diagnostics
    report = configuration_diagnostics()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print('Configuration:', report['directory'])
        print('Configuration SHA-256:', report['sha256'])
        print('Effective SHA-256:', report['effective_sha256'])
        for name, info in report['files'].items():
            print(f"{name}: {info['status']}" + (f" — {info['warning']}" if 'warning' in info else ''))
        print('Restart ICOCR after editing configuration.')
    return 1 if report['warnings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
