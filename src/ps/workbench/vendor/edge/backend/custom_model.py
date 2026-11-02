"""Explicit register/serial model adapter, preserving reviewed original run_next."""
import copy,shutil,sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from custom_fixture import Integration
from custom_owner import CustomOwner
from custom_io import export

class ModelHarness(Integration):
    def runTest(self):pass
    def __init__(self,plan,directory):
        super().__init__();self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False);self.setUp()
        fc=ModuleType('fcntl');fc.LOCK_EX=2;fc.LOCK_NB=4;fc.flock=lambda *a:None
        try:
            with patch.dict(sys.modules,{'fcntl':fc}):self.owner=CustomOwner(self.s,self.b,self.lock,plan)
        except Exception:self.doCleanups();raise
    def run(self,key='custom_run_0001'):
        with patch('controlled_trial_executor._one',side_effect=self.one):return self.owner.run(key)
    def step(self,key,selection=None):
        with patch('controlled_trial_executor._one',side_effect=self.one):return self.owner.step(key,selection)
    def save(self):
        stats=export(self.directory/'export',self.owner)
        if self.owner.state not in ('READY','RUNNING','AWAITING_SELECTION'):shutil.copytree(self.s.root,self.directory/'register_model_session')
        return stats
    def close(self):
        if self.owner.state in ('READY','RUNNING','AWAITING_SELECTION'):self.owner.request_stop()
        self.doCleanups()

from custom_backend import Backend as PublicBackend

class Backend(PublicBackend):
    """Test-only adaptation of the public facade, excluded from the real path."""
    def __init__(self,harness):
        super().__init__(harness.owner,step=harness.step,save=harness.save)
