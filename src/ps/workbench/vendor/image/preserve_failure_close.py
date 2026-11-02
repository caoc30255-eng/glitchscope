# Run only in the failed session_00000026 kernel, after verifying the new ZIP.
# This never retries initialization, resets hardware or transmits a frame.
from pathlib import Path
import ast,json,hashlib,os,uuid

assert board_session.root.name=='session_00000026', '只用于本次26初始化失败现场'
assert board_session.current is None and image_web.pilot is None, '已有试验计划或在途记录，停止收尾'
assert not (board_session.root/'EXECUTOR').exists(), '已创建图片执行器，停止收尾'
counts={key:int(buses['SYS'].read(offset)) for key,offset in [('retire_count',0x18),('grant_count',0x1c)]}
assert counts=={'retire_count':0,'grant_count':0}, '已有实际试验计数，停止收尾'
nb_path=candidate/'image_upload.ipynb'
raw_notebook=nb_path.read_bytes();nb=json.loads(raw_notebook)
actual=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
fixed=[(candidate/('step%d_complete_cell.py'%i)).read_text(encoding='utf-8') for i in range(1,4)]
def code_hash(source):
    return hashlib.sha256(ast.dump(ast.parse(source,feature_version=(3,8)),include_attributes=False).encode()).hexdigest()
comparison=[]
for i,(a,b) in enumerate(zip(actual,fixed),1):
    try:comparison.append(dict(cell=i,exact_text_match=a==b,AST_match=code_hash(a)==code_hash(b)))
    except SyntaxError as exc:comparison.append(dict(cell=i,exact_text_match=a==b,AST_match=False,error=str(exc)))
report=dict(session=board_session.root.name,reason='NOTEBOOK_CODE_DIFFERS_FROM_FIXED_CELLS',
    code_cells=len(actual),comparison=comparison,session_fault=bool(board_session.fault),
    receiver_fault=bool(control_uart.fault),image_executor_created=False,counts=counts,
    actual_notebook_sha256=hashlib.sha256(raw_notebook).hexdigest(),automatic_retry=False)
if control_uart.context:report['receiver_snapshot']=control_uart.pending_snapshot(limit=65536)
folder=board_session.root/('WEB_START_FAILURE_'+uuid.uuid4().hex);folder.mkdir()
for name,raw in {'notebook_original.ipynb':raw_notebook,
                 'diagnostic.json':json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')}.items():
    with (folder/name).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
directory_fd=os.open(str(folder),os.O_RDONLY)
try:os.fsync(directory_fd)
finally:os.close(directory_fd)
directory_fd=os.open(str(board_session.root),os.O_RDONLY)
try:os.fsync(directory_fd)
finally:os.close(directory_fd)
board_session.journal.record('web_setup_aborted_before_image_plan',diagnostic=str(folder),**counts)
board_session.close()
print(json.dumps(report,ensure_ascii=False,indent=2))
print('失败现场和原Notebook已保存，接收器及日志已关闭:',folder)
print('不要重跑第2步；保持STM32运行，后续用新内核、新会话。')
