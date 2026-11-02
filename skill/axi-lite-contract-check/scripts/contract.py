"""Logical uint32 register contract. A bus supplies already-decoded integer words."""
import argparse, copy, json, sys, threading
from pathlib import Path
def uint(v):
    if isinstance(v,bool):raise ValueError('BOOL_NOT_WORD')
    n=int(v,0) if isinstance(v,str) else v
    if type(n) is not int or not 0<=n<=0xffffffff:raise ValueError('WORD_RANGE')
    return n
def validate(c):
    if type(c.get('schema')) is not int or c.get('schema')!=1 or type(c.get('word_bits')) is not int or c.get('word_bits')!=32:raise ValueError('CONTRACT_SCHEMA')
    if c.get('addressing') not in ('offset','absolute'):raise ValueError('ADDRESSING_REQUIRED')
    base,span=uint(c['base']),uint(c['span']);seen=set();offsets=set()
    if base%4 or span<4 or base+span>2**32:raise ValueError('BANK_RANGE')
    for r in c['registers']:
        off=uint(r['offset'])
        if off%4 or off+4>span or off in offsets or r['name'] in seen:raise ValueError('REGISTER_RANGE_OR_DUPLICATE')
        seen.add(r['name']);offsets.add(off)
        if r['access'] not in ('RO','RW','WO','W1C','MIXED'):raise ValueError('ACCESS')
        if r.get('read_effect','none') not in ('none','clear'):raise ValueError('READ_EFFECT')
        uint(r.get('write_mask',0xffffffff))
        if 'expected' in r:uint(r['expected'])
        validate_fields(r)
    return c
def field_mask(f):return ((1<<f['width'])-1)<<f['lsb']
def validate_fields(r):
    fs=r.get('fields')
    if r['access']!='MIXED':
        if fs is not None:raise ValueError('FIELDS_REQUIRE_MIXED_REGISTER')
        return
    if not isinstance(fs,list) or not fs:raise ValueError('MIXED_FIELDS_REQUIRED')
    occupied=0;names=set();writable=0
    for f in fs:
        if type(f.get('lsb')) is not int or type(f.get('width')) is not int or f['lsb']<0 or f['width']<1 or f['lsb']+f['width']>32:raise ValueError('FIELD_RANGE')
        mask=field_mask(f)
        if mask&occupied or f['name'] in names:raise ValueError('FIELD_OVERLAP_OR_DUPLICATE')
        occupied|=mask;names.add(f['name'])
        if f['access'] not in ('RO','RW','W1C','PULSE','RESERVED'):raise ValueError('FIELD_ACCESS')
        if f.get('read_effect','none') not in ('none','clear'):raise ValueError('FIELD_READ_EFFECT')
        if f['access'] in ('RO','RESERVED'):
            if 'write_value' not in f or uint(f['write_value'])>=2**f['width']:raise ValueError('EXPLICIT_NONWRITABLE_WRITE_VALUE_REQUIRED')
        else:writable|=mask
    if occupied!=0xffffffff:raise ValueError('ALL_BITS_REQUIRE_FIELD_OR_RESERVED_POLICY')
    if 'write_mask' in r and uint(r['write_mask'])!=writable:raise ValueError('WRITE_MASK_FIELDS_DISAGREE')
def read_effect(r):return r.get('read_effect','none')!='none' or any(f.get('read_effect','none')!='none' for f in (r.get('fields') or []))
def masks(r,access):return sum(field_mask(f) for f in (r.get('fields') or []) if f['access'] in access)
def neutral(r):return sum(uint(f['write_value'])<<f['lsb'] for f in r['fields'] if f['access'] in ('RO','RESERVED'))

def choose_method(bus, explicit, options):
    if explicit:
        method=getattr(bus,explicit,None)
        if not callable(method):raise ValueError('METHOD_MISSING:'+explicit)
        return method
    found=[getattr(bus,n) for n in options if callable(getattr(bus,n,None))]
    if len(found)!=1:raise ValueError('METHOD_AMBIGUOUS_OR_MISSING')
    return found[0]
class RegisterBank:
    def __init__(self,bus,contract):
        self.c=validate(copy.deepcopy(contract));self.regs={r['name']:r for r in self.c['registers']}
        self._read=choose_method(bus,contract.get('read_method'),['read','read32'])
        self._write=choose_method(bus,contract.get('write_method'),['write','write32']) if any(r['access']!='RO' for r in self.regs.values()) else None
        self.lock=threading.RLock()
    def address(self,r):return uint(r['offset'])+(uint(self.c['base']) if self.c['addressing']=='absolute' else 0)
    def read(self,name,allow_clear=False):
        r=self.regs[name]
        if r['access']=='WO':raise ValueError('WRITE_ONLY')
        if read_effect(r) and not allow_clear:raise ValueError('READ_CLEAR_REQUIRES_EXPLICIT_CALLER_INTENT')
        with self.lock:return uint(self._read(self.address(r)))
    def write(self,name,value):
        r=self.regs[name];value=uint(value)
        if r['access']=='RO':raise ValueError('READ_ONLY')
        if r['access']=='MIXED':
            fixed=masks(r,('RO','RESERVED'))
            if value&fixed!=neutral(r):raise ValueError('NONWRITABLE_FIELD_WRITE_POLICY')
        elif value & ~uint(r.get('write_mask',0xffffffff)):raise ValueError('RESERVED_WRITE_BITS')
        with self.lock:self._write(self.address(r),value)
    def update_bits(self,name,mask,value):
        r=self.regs[name];mask,value=uint(mask),uint(value)
        if r['access'] not in ('RW','MIXED') or read_effect(r):raise ValueError('RMW_SEMANTICS_UNSAFE')
        allowed=masks(r,('RW',)) if r['access']=='MIXED' else uint(r.get('write_mask',0xffffffff))
        if mask&~allowed or value&~mask:raise ValueError('RMW_MASK_MUST_TARGET_RW_FIELDS_ONLY')
        if not mask:return
        with self.lock:
            current=self.read(name)
            if r['access']=='MIXED':word=neutral(r)|((current&allowed)&~mask)|value
            else:word=(current&~mask)|value # Do not silently discard undocumented RO/reserved bits.
            self.write(name,word)
    def write_fields(self,name,updates):
        r=self.regs[name]
        if r['access']!='MIXED' or not updates:raise ValueError('MIXED_FIELD_UPDATE_REQUIRED')
        fields={f['name']:f for f in r['fields']}
        if set(updates)-set(fields):raise ValueError('UNKNOWN_FIELD')
        for n,v in updates.items():
            if fields[n]['access'] not in ('RW','W1C','PULSE') or uint(v)>=2**fields[n]['width']:raise ValueError('FIELD_WRITE_VALUE')
        with self.lock:
            missing=[f for f in r['fields'] if f['access']=='RW' and f['name'] not in updates]
            if missing and read_effect(r):raise ValueError('EXPLICIT_ALL_RW_VALUES_REQUIRED_FOR_READ_CLEAR')
            current=self.read(name) if missing else 0
            word=neutral(r)|sum(current&field_mask(f) for f in missing)
            for n,v in updates.items():word|=uint(v)<<fields[n]['lsb']
            self.write(name,word)
    def identities(self):
        result=[]
        for n,r in self.regs.items():
            if 'expected' in r:
                if r['access']!='RO' or r.get('read_effect','none')!='none':raise ValueError('UNSAFE_IDENTITY_REGISTER')
                a=self.read(n);result.append(dict(register=n,actual=a,expected=uint(r['expected']),matched=a==uint(r['expected'])))
        return result
class FakeBus:
    """Offline word model only; not a replacement for physical bus verification."""
    def __init__(self,words):self.words={uint(k):uint(v) for k,v in words.items()};self.calls=[]
    def read(self,a):self.calls.append(['read',a]);return self.words.get(a,0)
    def write(self,a,v):self.calls.append(['write',a,v]);self.words[a]=v
class SemanticBus(FakeBus):
    """Register-value semantics only: no AXI timing, analog behavior or concurrent master simulation."""
    def __init__(self,contract,words):
        super().__init__(words);self.c=validate(copy.deepcopy(contract));self.pulses=[]
        self.regs={uint(r['offset'])+(uint(contract['base']) if contract['addressing']=='absolute' else 0):r for r in contract['registers']}
    def read(self,a):
        r=self.regs[a]
        if r['access']=='WO':raise ValueError('MODEL_WRITE_ONLY')
        value=super().read(a)
        if r.get('read_effect','none')=='clear':self.words[a]=0
        else:
            clear=sum(field_mask(f) for f in (r.get('fields') or []) if f.get('read_effect','none')=='clear')
            self.words[a]=value&~clear
        return value
    def write(self,a,v):
        r=self.regs[a];self.calls.append(['write',a,v]);current=self.words.get(a,0)
        if r['access']=='RO':raise ValueError('MODEL_READ_ONLY')
        if r['access']=='W1C':self.words[a]=current&~v
        elif r['access']=='MIXED':
            for f in r['fields']:
                mask=field_mask(f)
                if f['access']=='RW':current=(current&~mask)|(v&mask)
                elif f['access']=='W1C':current&=~(v&mask)
                elif f['access']=='PULSE' and v&mask:self.pulses.append(dict(address=a,field=f['name'],value=(v&mask)>>f['lsb']))
            self.words[a]=current&~masks(r,('PULSE',))
        else:self.words[a]=v

def main():
    p=argparse.ArgumentParser();p.add_argument('--contract',required=True);p.add_argument('--words',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();c=json.loads(Path(a.contract).read_text(encoding='utf-8'));bus=FakeBus(json.loads(Path(a.words).read_text(encoding='utf-8')))
    with Path(a.output).open('x',encoding='utf-8') as f:
        try:
            b=RegisterBank(bus,c);ids=b.identities();ok=bool(ids) and all(i['matched'] for i in ids)
            r=dict(status='PASS_OFFLINE_IDENTITIES' if ok else 'BLOCKED_IDENTITY',identities=ids,calls=bus.calls,hardware_access=False)
        except Exception as e:r=dict(status='BLOCKED',error=str(e),hardware_access=False)
        json.dump(r,f,indent=2)
    print(json.dumps(r));return 0 if r['status'].startswith('PASS_') else 2
if __name__=='__main__':sys.exit(main())
