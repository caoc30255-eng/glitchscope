"""Compatibility entry for the new isolated EdgeAI delivery; read-only."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from edge_package import verify
if __name__=='__main__':print('PASS EdgeAI fixed files:',verify(notebooks=True),'hardware_access: false')
