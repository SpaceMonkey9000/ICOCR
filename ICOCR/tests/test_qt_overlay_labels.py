"""Source-only checks for full overlay text generation (no Qt required)."""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / 'qt_recognition_overlay.py'
TREE = ast.parse(SRC.read_text(encoding='utf-8'))
FN = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'overlay_text')

class OverlayLabelTests(unittest.TestCase):
    def test_description_is_not_discarded(self):
        presenter = types.ModuleType('app_presenters')
        presenter.overlay_label = lambda row, loaded: (row['text'] + '\n' + row.get('function_summary', 'No database match'), '#00ff00')
        catalog = types.ModuleType('component_catalog')
        catalog.record_description = lambda record: record.get('entry_function', '') or record.get('component_function', '')
        old_presenter = sys.modules.get('app_presenters')
        old_catalog = sys.modules.get('component_catalog')
        sys.modules['app_presenters'] = presenter
        sys.modules['component_catalog'] = catalog
        try:
            namespace = {}
            exec(compile(ast.Module(body=[FN], type_ignores=[]), str(SRC), 'exec'), namespace)
            title, description, colour = namespace['overlay_text']({
                'text': 'SN74HC00',
                'selected_database_match': {'entry_function': 'Quad two-input NAND gate'}
            }, True)
            self.assertEqual(title, 'SN74HC00')
            self.assertEqual(description, 'Quad two-input NAND gate')
            self.assertEqual(colour, '#00ff00')
        finally:
            if old_presenter is None: sys.modules.pop('app_presenters', None)
            else: sys.modules['app_presenters'] = old_presenter
            if old_catalog is None: sys.modules.pop('component_catalog', None)
            else: sys.modules['component_catalog'] = old_catalog

    def test_missing_match_does_not_invent_description(self):
        presenter = types.ModuleType('app_presenters')
        presenter.overlay_label = lambda row, loaded: ('ABC\nNo database match', '#fff')
        catalog = types.ModuleType('component_catalog')
        catalog.record_description = lambda record: ''
        with patch.dict(sys.modules, {'app_presenters': presenter, 'component_catalog': catalog}):
            namespace = {}
            exec(compile(ast.Module(body=[FN], type_ignores=[]), str(SRC), 'exec'), namespace)
            self.assertEqual(namespace['overlay_text']({'text': 'ABC'}, True)[1], 'No database match')

if __name__ == '__main__': unittest.main()
