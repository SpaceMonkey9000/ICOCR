"""Single command entry point for the application and maintenance tools."""
import argparse
import os
import subprocess
import sys
from project_paths import ROOT

SCRIPTS = {
    'run': 'app.py',
    'config-check': 'tools/check_config.py',
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Default: run. Tool arguments follow the command; e.g. config-check --json.'))
    parser.add_argument('command', nargs='?', default='run', choices=list(SCRIPTS))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    env = os.environ.copy()
    forwarded = args.arguments
    if args.command == 'run':
        run_parser = argparse.ArgumentParser(prog='manage.py run')
        devices = ('auto', 'cpu', 'cuda')
        # argparse does not check defaults against choices: an invalid
        # ICLENS_DEVICE (e.g. "gpu" or "CUDA ") reached the app unchecked.
        default = env.get('ICLENS_DEVICE', 'auto').strip().lower() or 'auto'
        if default not in devices:
            print(f'manage.py: ignoring ICLENS_DEVICE={env["ICLENS_DEVICE"]!r} '
                  f'(expected one of {", ".join(devices)}); using auto', file=sys.stderr)
            default = 'auto'
        run_parser.add_argument('--device', choices=devices, default=default)
        env['ICLENS_DEVICE'] = run_parser.parse_args(forwarded).device
        forwarded = []
    command = [sys.executable, str(ROOT/SCRIPTS[args.command]), *forwarded]
    try:
        return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
