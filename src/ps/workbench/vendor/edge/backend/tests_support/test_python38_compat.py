from pathlib import Path
import sys, unittest, ast
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'host'))
from ps_path_compat import path_within


class Python38Tests(unittest.TestCase):
    def test_contained_file(self):
        self.assertTrue(path_within(ROOT/'host/ps_path_compat.py', ROOT))
    def test_parent_escape_rejected(self):
        self.assertFalse(path_within(ROOT/'../outside', ROOT))
    def test_same_prefix_sibling_rejected(self):
        self.assertFalse(path_within(ROOT.with_name(ROOT.name+'_other')/'file', ROOT))
    def test_production_syntax_is_python38_and_no_new_path_API(self):
        for path in [*list((ROOT/'host').glob('*.py')), *list((ROOT/'reference').glob('*.py')), ROOT/'read_only_probe.py']:
            text = path.read_text(encoding='utf-8')
            ast.parse(text, feature_version=(3, 8))
            self.assertNotIn('.is_relative_to(', text, path)


if __name__ == '__main__': unittest.main()
