"""Test pure coordinate helpers without requiring a graphical Qt session."""
import ast
from pathlib import Path
import math
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'qt_recognition_overlay.py'
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('point_list', 'translate_box')]
namespace = {'math': math}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), namespace)

class OverlayGeometryTests(unittest.TestCase):
    def test_crop_translation_uses_ocr_truncation(self):
        roi=(.25,.1,.75,.9)
        self.assertEqual(namespace['translate_box']([[0,0],[100,0],[100,20],[0,20]],roi,(1920,1080)),
                         [(480,108),(580,108),(580,128),(480,128)])

    def test_invalid_boxes_hidden(self):
        self.assertEqual(namespace['point_list'](None),[])
        self.assertEqual(namespace['point_list']([[float('nan'),1],[0,0],[2,0]]),[])

    def test_detector_rectangle(self):
        self.assertEqual(namespace['point_list']([1,2,5,8]),[(1,2),(5,2),(5,8),(1,8)])

if __name__ == '__main__': unittest.main()
