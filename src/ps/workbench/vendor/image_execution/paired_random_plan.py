"""Deterministic offline random schedule, not a claim of observed bit errors."""
from multi_point_profile import MultiPointProfile

ALGORITHM='SHA256_COUNTER_REJECTION_V1'
IMAGE_SHA='6192177385d8d6a5513d80d5a53a45c891fb34f8f8603fcda53fb91172215330'
DEFAULT_SEED=20261018

class Draws:
    def __init__(self,seed):
        if type(seed) is not int or not 0<=seed<2**64:raise ValueError('Unsigned64 seed required')
        self.seed=seed;self.counter=0
    def below(self,bound):
        import hashlib
        if type(bound) is not int or not 0<bound<=2**32:raise ValueError('Positive bounded integer required')
        limit=2**256-(2**256%bound)
        while True:
            word=int.from_bytes(hashlib.sha256(b'PYNQ_RANDOM_IMAGE_V1\0'+self.seed.to_bytes(8,'big')+
                self.counter.to_bytes(8,'big')).digest(),'big')
            self.counter+=1
            if word<limit:return word%bound

def make_schedule(seed=DEFAULT_SEED, *, source_sha256=IMAGE_SHA, receiver_B=None):
    receiver_B={"d":3,"s":-1} if receiver_B is None else dict(receiver_B)
    if set(receiver_B)!={"d","s"} or type(receiver_B["d"]) is not int or type(receiver_B["s"]) is not int or receiver_B["d"] not in (1,2,3,4) or not -2<=receiver_B["s"]<=3-receiver_B["d"]:raise ValueError("Illegal uniform receiver B profile")
    if type(source_sha256) is not str or len(source_sha256)!=64 or any(c not in "0123456789abcdef" for c in source_sha256):raise ValueError("Exact source SHA256 required")
    rng=Draws(seed);items=[]
    for index in range(64):
        count=rng.below(256)
        # Zero is disabled TYPE3A; no first-byte/bit/phase/width is invented.
        if count:
            offset=rng.below(257-count);bit=rng.below(8)
            phase=5+rng.below(40);width=1+rng.below(45-phase)
            profile=dict(first_byte=20+offset,count=count,bit=bit,phase=phase,width=width)
        else:profile=None
        items.append(dict(item_index=index,client_request_id='image_%02d'%index,
            count=count,profile=profile,receiver_B=dict(receiver_B)))
    return dict(schema='RANDOM_IMAGE_PLAN_V0_1',algorithm=ALGORITHM,seed=seed,width=128,height=128,
        source_sha256=source_sha256,item_bytes=256,item_total=64,max_records_including_CONFIG=65,
        count_range_inclusive=[0,255],bit_range_inclusive=[0,7],phase_ticks_inclusive=[5,44],
        width_ticks_rule='uniform integer 1..45-phase; phase chosen first',life_clock_hz=50000000,
        position_rule='uniform payload start 0..256-count inclusive after choosing count',
        same_bit_phase_width_within_ITEM=True,header_or_CRC_targeting=False,
        automatic_retry_allowed=False,training_authorized=False,production_billing_finalized=False,
        CAP06_scope='FIRST_POINT_ONLY',all_points_waveform_verified=False,items=items)

def validate_schedule(schedule):
    if type(schedule) is not dict or schedule!=make_schedule(schedule.get('seed'),source_sha256=schedule.get('source_sha256'),receiver_B=schedule.get('items',[{}])[0].get('receiver_B')):
        raise ValueError('Schedule differs from deterministic bounded random plan')
    from ch1_completion_ledger import _codec
    for entry in schedule['items']:
        if entry['profile'] is not None:
            p=MultiPointProfile(**entry['profile'])
            p.validate(_codec().encode_item(1,1,1,entry['item_index'],64,0,0,bytes(256)))
    return True
