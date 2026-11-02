"""Packet decoding, masked assembly and receiver-only repair. No source image input."""
import binascii,copy,math,statistics,struct,time,zlib
from labutil import *

def crc(raw):return binascii.crc_hqx(raw,0xffff)
def config_decode(raw):
    require(len(raw)>=58 and raw[:2]==b'\x55\xcc','CONFIG_FRAME')
    ver,run,image,fmt,order,w,h,n,total,chunk,imagehash=struct.unpack('>BIBBBHHIHH32s',raw[2:54])
    require(ver==2 and fmt==1 and order==0 and n==w*h and 1<=total<=64 and 1<=chunk<=512,'CONFIG_FIELDS')
    require(total==(n+chunk-1)//chunk and len(raw)==56+2*total and crc(raw[2:-2])==int.from_bytes(raw[-2:],'big'),'CONFIG_CRC_OR_SIZE')
    return dict(run_id=run,image_id=image,width=w,height=h,total_bytes=n,item_total=total,chunk_size=chunk,
        image_sha256=imagehash.hex(),item_crcs=[int.from_bytes(raw[54+2*i:56+2*i],'big') for i in range(total)],raw_sha256=sha(raw))

def decode_packet(raw,lane,identity,config,capture_valid=True):
    require(capture_valid,'CAPTURE_UNKNOWN');f=id_fields(identity)
    if lane in ('A','B'):
        require(len(raw)>=22 and raw[:2]==b'\x55\xaa','ITEM_HEADER')
        v,run,image,trial,index,total,attempt,route,src_crc,size=struct.unpack('>BIBHHHBBHH',raw[2:20])
        require(0<=index<config['item_total'],'ITEM_INDEX')
        require(len(raw)==22+size and total==config['item_total'] and src_crc==config['item_crcs'][index],'ITEM_SIZE_CONFIG_CRC')
        payload=raw[20:-2];flags=None;status=None
    else:
        require(lane=='STM' and len(raw)>=20 and raw[:2]==b'\x55\xbb','REPORT_HEADER')
        v,run,image,trial,index,attempt,route,flags,status,size=struct.unpack('>BIBHHBBBBH',raw[2:18])
        require(len(raw)==20+size and flags<=15 and status in (0,1,2,3),'REPORT_FIELDS')
        require(crc(raw[2:-2])==int.from_bytes(raw[-2:],'big'),'REPORT_CRC_UNKNOWN')
        payload=raw[18:-2]
    require(v==2 and run==config['run_id'] and image==config['image_id'] and 0<=index<config['item_total'],'IMAGE_NAMESPACE')
    require(all(f[k]==value for k,value in [('run_id',run),('image_id',image),('trial_id',trial),('item_index',index),('attempt_id',attempt),('route_mode',route)]),'PACKET_IDENTITY_MISMATCH')
    require(size==min(config['chunk_size'],config['total_bytes']-index*config['chunk_size']),'PAYLOAD_LENGTH')
    return dict(lane=lane,item_index=index,identity_hex=hex_identity(identity),payload_hex=payload.hex(),
        payload_crc_ok=crc(payload)==config['item_crcs'][index],frame_crc_ok=crc(raw[2:-2])==int.from_bytes(raw[-2:],'big'),
        uart_flags=flags,result_status=status,raw_sha256=sha(raw),capture_valid=True)

def decode_samples(raw,start,deadline):
    require(len(raw)%10==0,'SAMPLE_LENGTH');out=[];previous=start
    for i in range(0,len(raw),10):
        w=int.from_bytes(raw[i:i+10],'big');tick=w&((1<<64)-1)
        require(w>>76==0 and start<=tick<deadline and tick>=previous and (w>>64)&15==0,'SAMPLE_FLAGS_OR_WINDOW')
        out.append((w>>68)&255);previous=tick
    return bytes(out)

def ch1_descriptor(raw):
    fields=[('epoch',32),('reserved',1),('identity',256),('record_id',32),('kind',2),('reason',8),('raw_count',16),('start',64),('deadline',64),('close',64),('frame_valid',1),('report_status',8),('report_flags',8),('management_status',16),('uart_errors',32),('observed_flags',4),('first_error_tick',64)]
    require(len(raw)==84,'CH1_DESCRIPTOR');word=int.from_bytes(raw,'big');left=672;out={}
    for k,w in fields:left-=w;out[k]=(word>>left)&((1<<w)-1)
    require(not out['reserved'] and out['frame_valid']==1 and out['reason']==1 and out['uart_errors']==0,'CH1_CAPTURE_UNKNOWN')
    return out

class Assembler:
    def __init__(self,config,lane):self.config=copy.deepcopy(config);self.lane=lane;self.blocks={};self.unknown={};self.stopped=False
    def add(self,packet,reference):
        require(not self.stopped,'ASSEMBLER_STOPPED');i=packet['item_index'];require(packet['lane']==self.lane,'LANE')
        require(isinstance(i,int) and 0<=i<self.config['item_total'],'BLOCK_INDEX')
        require(len(bytes.fromhex(packet['payload_hex']))==min(self.config['chunk_size'],self.config['total_bytes']-i*self.config['chunk_size']),'BLOCK_LENGTH')
        prior=self.blocks.get(i)
        if prior:
            require(prior['packet']==packet,'BLOCK_CONFLICT; explicit attempt selection required');return 'DUPLICATE'
        self.blocks[i]=dict(packet=copy.deepcopy(packet),reference=copy.deepcopy(reference));self.unknown.pop(i,None);return 'ACCEPTED'
    def mark_unknown(self,index,reason):
        require(not self.stopped and isinstance(index,int) and 0<=index<self.config['item_total'],'UNKNOWN_INDEX_OR_STOPPED')
        require(index not in self.blocks,'UNKNOWN_CONFLICTS_WITH_SAVED_BLOCK');self.unknown[index]=reason
    def stop(self):self.stopped=True
    def render(self):
        data=bytearray(self.config['total_bytes']);missing=bytearray(b'\xff'*len(data))
        for i,b in self.blocks.items():
            raw=bytes.fromhex(b['packet']['payload_hex']);offset=i*self.config['chunk_size'];data[offset:offset+len(raw)]=raw;missing[offset:offset+len(raw)]=b'\0'*len(raw)
        return bytes(data),bytes(missing),dict(blocks=copy.deepcopy(list(self.blocks.values())),unknown=self.unknown,
            complete_capture=not any(missing),placeholders_under_missing_mask=True,origin='OFFLINE_REAL_EVIDENCE_REPLAY',stopped=self.stopped)

def png(path,data,width,height):
    require(len(data)==width*height,'PNG_SIZE')
    def chunk(kind,payload):return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    raw=b''.join(b'\0'+data[y*width:(y+1)*width] for y in range(height))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

def median_visual(data,missing,width,height):
    out=bytearray(data)
    for y in range(height):
        for x in range(width):
            i=y*width+x
            if missing[i]:continue
            values=[data[yy*width+xx] for yy in range(max(0,y-2),min(height,y+3)) for xx in range(max(0,x-2),min(width,x+3)) if not missing[yy*width+xx]]
            estimate=int(statistics.median(values))
            if abs(estimate-data[i])>8:out[i]=estimate
    return bytes(out)

_PREFIX={}
def burst_candidates(raw,expected_crc):
    """Unknown-position contiguous same-bit burst model, using receiver CRC only."""
    n=len(raw)
    if crc(raw)==expected_crc:return [raw]
    if n not in _PREFIX:
        zero=bytes(n);initial=crc(zero);prefix=[]
        for bit in range(8):
            p=[0]
            for i in range(n):
                v=bytearray(zero);v[i]=1<<bit;p.append(p[-1]^crc(v)^initial)
            prefix.append(p)
        _PREFIX[n]=prefix
    syndrome=crc(raw)^expected_crc;out=set()
    for bit,prefix in enumerate(_PREFIX[n]):
        seen={}
        for end,value in enumerate(prefix):
            for start in seen.get(value^syndrome,[]):
                if 1<=end-start<=255:
                    candidate=bytearray(raw)
                    for j in range(start,end):candidate[j]^=1<<bit
                    candidate=bytes(candidate)
                    if crc(candidate)==expected_crc:out.add(candidate)
            seen.setdefault(value,[]).append(end)
    return sorted(out)

def spatial_score(candidate,index,base,width,height,chunk):
    offset=index*chunk;end=offset+len(candidate)
    def pixel(pos):return candidate[pos-offset] if offset<=pos<end else base[pos]
    score=0
    for i,v in enumerate(candidate):
        pos=offset+i;y,x=divmod(pos,width)
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
            yy,xx=y+dy,x+dx
            if 0<=yy<height and 0<=xx<width:score+=min(96,abs(v-pixel(yy*width+xx)))
    return score

def repair(config,lanes,method='crc_burst_B'):
    """Only receiver config/checksums and received blocks; never source pixels or fault schedule."""
    require('B' in lanes,'B_REQUIRED');base,missing,trace=lanes['B'].render();original_missing=missing;estimated=bytearray(len(base));out=bytearray(base);uncertain=bytearray(missing);notes=[]
    if method=='visual_median_B':
        out=bytearray(median_visual(base,missing,config['width'],config['height']));uncertain=bytearray(255 if not m else m for m in missing)
        estimated=bytearray(255 if a!=b else 0 for a,b in zip(base,out))
    else:
        require(method in ('crc_select','crc_burst_B','crc_burst_multi'),'METHOD')
        for index in range(config['item_total']):
            available={name:bytes.fromhex(a.blocks[index]['packet']['payload_hex']) for name,a in lanes.items() if index in a.blocks}
            offset=index*config['chunk_size'];n=min(config['chunk_size'],config['total_bytes']-offset);crc_value=config['item_crcs'][index]
            preferred=['B'] if method=='crc_burst_B' else ['B','A','STM']
            available={k:available[k] for k in preferred if k in available}
            clean=next(((name,raw) for name,raw in available.items() if crc(raw)==crc_value),None)
            candidates=set()
            if clean:selected=clean[1];source=clean[0];candidates.add(selected)
            elif method!='crc_select':
                for raw in available.values():candidates.update(burst_candidates(raw,crc_value))
                selected=min(candidates,key=lambda b:(spatial_score(b,index,base,config['width'],config['height'],config['chunk_size']),b)) if candidates else base[offset:offset+n]
                source='CRC_BURST_MODEL_WITH_SPATIAL_RANKING' if candidates else 'B_UNREPAIRED' if 'B' in available else 'MISSING_NO_ACCEPTED_SOURCE'
            else:selected=base[offset:offset+n];source='B_UNREPAIRED' if 'B' in available else 'MISSING_NO_ACCEPTED_SOURCE'
            out[offset:offset+n]=selected
            # Only actual selected received data can fill a missing receive slot.
            # Estimates have their own mask and retain the original missing area.
            if clean:missing=missing[:offset]+b'\0'*n+missing[offset+n:]
            if not clean and candidates:estimated[offset:offset+n]=b'\xff'*n
            uncertain[offset:offset+n]=bytes([0 if clean else 255])*n
            notes.append(dict(item_index=index,selection=source,candidate_count=len(candidates),crc_matches=crc(selected)==crc_value,
                lossless_per_block_claimed=False))
    raw=bytes(out);whole_ok=not any(missing) and sha(raw)==config['image_sha256']
    if whole_ok:uncertain=bytearray(len(raw))
    return dict(data=raw,missing=missing,original_B_missing=original_missing,estimated=bytes(estimated),modified=bytes(255 if a!=b else 0 for a,b in zip(base,raw)),uncertain=bytes(uncertain),
        metadata=dict(algorithm=method,version='RECEIVER_CRC_BURST_SPATIAL_V0_1_1',receiver_lanes=list(lanes),
            origin='OFFLINE_REAL_EVIDENCE_REPLAY',whole_received_config_SHA_verified=whole_ok,
            conclusion='LOSSLESS_TO_RECEIVED_CONFIG_SHA' if whole_ok else 'VISUAL_OR_BURST_ESTIMATE_NOT_VERIFIED_CORRECT',
            source_image_used=False,fault_plan_used=False,blocks=notes,input_B_sha256=sha(base),output_sha256=sha(raw)))

def evaluate(source,candidate,mask):
    require(len(source)==len(candidate)==len(mask),'EVALUATION_SIZE');valid=[i for i,m in enumerate(mask) if not m]
    if not valid:return dict(known_pixels=0,missing=len(mask),error_pixels=None,MAE=None,PSNR=None)
    errors=[abs(source[i]-candidate[i]) for i in valid];mse=sum(v*v for v in errors)/len(valid)
    return dict(known_pixels=len(valid),missing=len(mask)-len(valid),error_pixels=sum(v!=0 for v in errors),
        MAE=sum(errors)/len(valid),PSNR=10*math.log10(255*255/mse) if mse else 'INF')
