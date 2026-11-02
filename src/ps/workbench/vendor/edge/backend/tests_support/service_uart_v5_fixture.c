#define SERVICE_FIXTURE
#include "../host/uartlite_service_v5.c"
static pthread_mutex_t device_lock=PTHREAD_MUTEX_INITIALIZER;
static uint8_t injected[4096];static uint32_t length,consumed,txcount,trigger;
static uint64_t origin;static uint32_t hwerror;
static uint64_t injected_gap;static uint32_t gap_at,stall_ms;
static uint32_t finite_fifo,generated,head,tail,queued,lost,hold_worker;
static uint8_t hardware_fifo[16];static uint64_t byte_period=43400u;
static uint32_t stall_before_tx,tx_stall_ms,peer_discarded;
static uint64_t peer_gap_limit,last_tx_time;
API void fixture_reset(const uint8_t *raw,uint32_t len,uint32_t when){
    pthread_mutex_lock(&device_lock);memcpy(injected,raw,len);length=len;consumed=txcount=0;
    trigger=when;origin=0;hwerror=0;injected_gap=0;gap_at=0xffffffff;stall_ms=0;
    finite_fifo=generated=head=tail=queued=lost=hold_worker=0;byte_period=43400u;
    stall_before_tx=tx_stall_ms=peer_discarded=0;peer_gap_limit=last_tx_time=0;
    pthread_mutex_unlock(&device_lock);
}
API void fixture_TX_pause(uint32_t before_word,uint32_t ms,uint32_t peer_timeout_ms){
    pthread_mutex_lock(&device_lock);stall_before_tx=before_word;tx_stall_ms=ms;
    peer_gap_limit=(uint64_t)peer_timeout_ms*1000000;pthread_mutex_unlock(&device_lock);
}
API uint32_t fixture_peer_discarded(void){uint32_t n;pthread_mutex_lock(&device_lock);n=peer_discarded;pthread_mutex_unlock(&device_lock);return n;}
API void fixture_finite_fifo(uint32_t period_ns){pthread_mutex_lock(&device_lock);finite_fifo=1;byte_period=period_ns;if(trigger==0)origin=service_clock();pthread_mutex_unlock(&device_lock);}
API void fixture_hold_worker(uint32_t hold){pthread_mutex_lock(&device_lock);hold_worker=hold;pthread_mutex_unlock(&device_lock);}
API uint32_t fixture_hardware_words(void){uint32_t n;pthread_mutex_lock(&device_lock);n=queued;pthread_mutex_unlock(&device_lock);return n;}
API uint32_t fixture_lost_words(void){uint32_t n;pthread_mutex_lock(&device_lock);n=lost;pthread_mutex_unlock(&device_lock);return n;}
void service_worker_wait(void){
    for(;;){
        uint32_t hold;pthread_mutex_lock(&device_lock);hold=hold_worker;pthread_mutex_unlock(&device_lock);
        if(!hold)return;
#ifdef _WIN32
        Sleep(1);
#else
        {struct timespec t={0,1000000};nanosleep(&t,NULL);}
#endif
    }
}
API void fixture_parser_stall(uint32_t ms){pthread_mutex_lock(&device_lock);stall_ms=ms;pthread_mutex_unlock(&device_lock);}
API void fixture_wire_gap(uint32_t index,uint32_t ms){pthread_mutex_lock(&device_lock);gap_at=index;injected_gap=(uint64_t)ms*1000000;pthread_mutex_unlock(&device_lock);}
void service_after_pop(void){
    uint32_t ms;pthread_mutex_lock(&device_lock);ms=stall_ms;stall_ms=0;pthread_mutex_unlock(&device_lock);
    if(!ms)return;
#ifdef _WIN32
    Sleep(ms);
#else
    {struct timespec t={ms/1000,(long)(ms%1000)*1000000};nanosleep(&t,NULL);}
#endif
}
API void fixture_error(uint32_t flags){pthread_mutex_lock(&device_lock);hwerror=flags;pthread_mutex_unlock(&device_lock);}
API uint32_t fixture_txcount(void){uint32_t n;pthread_mutex_lock(&device_lock);n=txcount;pthread_mutex_unlock(&device_lock);return n;}
uint32_t service_hw_read(uint32_t index){
    uint32_t produced=0,result=0xffffffff;uint64_t now=service_clock();
    pthread_mutex_lock(&device_lock);
    if(txcount>=trigger&&!peer_discarded){
        if(!origin)origin=now;
        while(produced<length&&now-origin>=(uint64_t)produced*byte_period+
                (produced>=gap_at?injected_gap:0))produced++;
    }
    if(finite_fifo){
        while(generated<produced){
            if(queued<16){hardware_fifo[tail]=injected[generated];tail=(tail+1)%16;queued++;}
            else{lost++;hwerror|=0x20;}
            generated++;
        }
        if(index==2){result=4u|(queued?1u:0u)|(queued==16?2u:0u)|hwerror;hwerror=0;}
        else if(index==0&&queued){result=hardware_fifo[head];head=(head+1)%16;queued--;consumed++;}
    }else{
        if(index==2){result=4u|(produced>consumed?1u:0u)|(produced-consumed>=16?2u:0u)|hwerror;hwerror=0;}
        else if(index==0&&consumed<produced)result=injected[consumed++];
    }
    pthread_mutex_unlock(&device_lock);return result;
}
void service_hw_write(uint32_t index,uint32_t value){
    uint32_t ms=0;uint64_t now;
    pthread_mutex_lock(&device_lock);
    if(index==1&&txcount+1==stall_before_tx){ms=tx_stall_ms;tx_stall_ms=0;}
    pthread_mutex_unlock(&device_lock);
    if(ms){
#ifdef _WIN32
        Sleep(ms);
#else
        {struct timespec t={ms/1000,(long)(ms%1000)*1000000};nanosleep(&t,NULL);}
#endif
    }
    pthread_mutex_lock(&device_lock);
    if(index==1&&value<=255){
        now=service_clock();
        if(last_tx_time&&peer_gap_limit&&now-last_tx_time>=peer_gap_limit)peer_discarded=1;
        last_tx_time=now;txcount++;
    }
    pthread_mutex_unlock(&device_lock);
}
