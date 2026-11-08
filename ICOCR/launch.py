"""Frozen entry point; startup failures remain visible without a console."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback


DEVICES=('auto','cpu','cuda')


def device_default(environ=os.environ):
    """ICLENS_DEVICE checked as in ``manage.py run`` (0.8.8): argparse does not
    check defaults against choices, so "gpu" or "CUDA " reached the app unchecked."""
    default=environ.get('ICLENS_DEVICE','auto').strip().lower() or 'auto'
    if default not in DEVICES:
        print(f'launch.py: ignoring ICLENS_DEVICE={environ["ICLENS_DEVICE"]!r} '
              f'(expected one of {", ".join(DEVICES)}); using auto',file=sys.stderr)
        default='auto'
    return default


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--device',choices=DEVICES,default=device_default())
    p.add_argument('--report')
    args=p.parse_args(argv)
    os.environ['ICLENS_DEVICE']=args.device
    from project_paths import DATA
    from user_paths import prepare_config
    prepare_config(DATA)
    # Import the real application in both modes. A runtime/OCR-only smoke test
    # cannot catch broken application imports in a frozen release.
    from app import VERSION, main as run
    if args.self_test:
        import tkinter as tk
        from project_paths import ROOT
        from ocr_runtime import create_engine, providers
        import numpy as np
        engine, runtime=create_engine(args.device,strict=args.device=='cuda')
        engine(np.full((64,256,3),255,dtype=np.uint8))
        root=tk.Tk();root.withdraw();root.iconbitmap(str(ROOT/'ICOCR.ico'));root.destroy()
        result={'ok':True,'version':VERSION,'providers':providers(engine),'device':args.device,'application_import':True}
        if args.report:Path(args.report).write_text(json.dumps(result,indent=2),'utf-8')
    else:
        run()
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        from user_paths import BASE
        folder=BASE/'ICSuite'/'ICOCR';folder.mkdir(parents=True,exist_ok=True)
        report=folder/'startup-error.log';report.write_text(traceback.format_exc(),'utf-8')
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw();messagebox.showerror('ICOCR startup failed',traceback.format_exc()+'\nLog: '+str(report));root.destroy()
        raise SystemExit(1)
