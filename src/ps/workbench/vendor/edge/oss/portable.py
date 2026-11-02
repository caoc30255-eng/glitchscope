"""PC tooling shim; actual deployment code is bound inside backend."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend/oss_runtime"))
from oss_portable import *
