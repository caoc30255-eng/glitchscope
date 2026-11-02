import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from notebook_code_compat import verify_notebook


class Compatibility(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=['from pathlib import Path\nvalue = 150\n',
                     'initialize(control_uart)\nstart(workspace, port=8765)\n',
                     'board_session.close()\n']
        self.paths=[]
        for i,source in enumerate(self.source):
            p=self.root/('%d.py'%i);p.write_text(source,encoding='utf-8');self.paths.append(p)
        self.nb=self.root/'run.ipynb'
    def check(self,cells,**kwargs):
        nb=dict(cells=[dict(cell_type='markdown',source=['guide'],metadata={})]+[
            dict(cell_type='code',source=s,outputs=kwargs.get('outputs',[]),execution_count=7,metadata={'saved':True}) for s in cells])
        self.nb.write_text(json.dumps(nb),encoding='utf-8');return verify_notebook(self.nb,self.paths)
    def test_original_matches(self):self.assertTrue(self.check(self.source)['exact_text_match'])
    def test_jupyter_trailing_newline_stripping(self):
        result=self.check([s.rstrip('\n') for s in self.source]);self.assertTrue(result['notebook_code_ast_match']);self.assertFalse(result['exact_text_match'])
    def test_CRLF_and_source_arrays(self):self.assertTrue(self.check([s.replace('\n','\r\n').splitlines(keepends=True) for s in self.source])['notebook_code_ast_match'])
    def test_comments_and_empty_lines(self):self.assertTrue(self.check(['# saved\n\n'+s for s in self.source])['notebook_code_ast_match'])
    def test_outputs_ignored(self):self.assertTrue(self.check(self.source,outputs=[dict(output_type='stream',text='READY True')])['notebook_code_ast_match'])
    def test_changed_clock_rejected(self):
        cells=list(self.source);cells[0]=cells[0].replace('150','100')
        with self.assertRaises(ValueError):self.check(cells)
    def test_removed_initialization_rejected(self):
        cells=list(self.source);cells[1]='start(workspace, port=8765)\n'
        with self.assertRaises(ValueError):self.check(cells)
    def test_added_command_rejected(self):
        with self.assertRaises(ValueError):self.check(self.source+['send_START()'])
    def test_reordered_commands_rejected(self):
        cells=list(self.source);cells[1]='start(workspace, port=8765)\ninitialize(control_uart)'
        with self.assertRaises(ValueError):self.check(cells)
    def test_syntax_error_rejected(self):
        cells=list(self.source);cells[1]='not valid Python ?'
        with self.assertRaises(ValueError):self.check(cells)
    def test_changed_string_literal_rejected(self):
        self.paths[0].write_text('name="first"\n',encoding='utf-8');cells=list(self.source);cells[0]='name="second"'
        with self.assertRaises(ValueError):self.check(cells)


if __name__=='__main__':unittest.main()
