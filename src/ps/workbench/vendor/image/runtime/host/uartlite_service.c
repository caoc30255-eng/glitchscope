/* Persistent RX collector. Python/disk pauses leave the worker active.
 * One serialized RX service, callable by worker or exchange; one TX owner.
 * Both latch every observed
 * clear-on-read UART error under the same lock. No FIFO reset/IRQ/clock IO. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <pthread.h>
#include <stdlib.h>
#include <stdint.h>
uint64_t service_rx_timestamp(void);
int service_rx_pending(void);
#define RX_TIMESTAMP() service_rx_timestamp()
#define RX_DATA_PENDING() service_rx_pending()
#define NATIVE_TEST
#include "uartlite_native.c"
typedef struct {
    volatile uint32_t *regs;
    uint32_t *ring,capacity,head,tail,count,errors,error_status,last_status;
    uint64_t *arrival_times,last_popped_time;
    uint64_t last_service,max_service_gap,worker_words,exchange_words,service_calls;
    uint64_t tx_words,first_tx,last_tx,max_tx_gap,max_tx_gap_index;
    uint64_t exchange_last_service,exchange_max_gap,worker_baseline,exchange_baseline;
    int exchange_active;
    int running,overflow,joined;
    pthread_t thread;pthread_mutex_t lock;
} Service;
static _Thread_local Service *current_service;
static uint64_t service_clock(void){
#ifdef _WIN32
    LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);
    return (uint64_t)((double)t.QuadPart*1e9/(double)f.QuadPart);
#else
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000000000u+(uint64_t)t.tv_nsec;
#endif
}
#ifdef SERVICE_FIXTURE
extern uint32_t service_hw_read(uint32_t index);
extern void service_hw_write(uint32_t index,uint32_t value);
extern void service_after_pop(void);
extern void service_worker_wait(void);
#define HW_READ(s,i) service_hw_read(i)
#define HW_WRITE(s,i,v) service_hw_write(i,v)
#else
#define HW_READ(s,i) ((s)->regs[i])
#define HW_WRITE(s,i,v) ((s)->regs[i]=(v))
#endif
static void note_status(Service *s,uint32_t f){
    s->last_status=f;
    if(f&0xe0u){s->errors|=f&0xe0u;if(!s->error_status)s->error_status=f;}
    if(f&~255u)s->overflow=2;
}
/* Caller holds lock. Each status observer must service RX too: a busy
 * transaction must not monopolize the mutex while leaving real FIFO unread.
 * Bounded to the actual 16-word FIFO per pass; no drop, reset or error clear. */
static uint32_t harvest(Service *s,int from_worker){
    uint32_t f,i=0,w;uint64_t now=service_clock();
    if(s->last_service&&now-s->last_service>s->max_service_gap)
        s->max_service_gap=now-s->last_service;
    s->last_service=now;s->service_calls++;
    if(s->exchange_active){
        if(s->exchange_last_service&&now-s->exchange_last_service>s->exchange_max_gap)
            s->exchange_max_gap=now-s->exchange_last_service;
        s->exchange_last_service=now;
    }
    f=HW_READ(s,2);note_status(s,f);
    while(!s->errors&&!s->overflow&&(f&1u)&&i<16){
        if(s->count==s->capacity){s->overflow=1;break;}
        w=HW_READ(s,0);s->ring[s->tail]=w;
        s->arrival_times[s->tail]=service_clock();
        s->tail=(s->tail+1)%s->capacity;s->count++;i++;
        if(from_worker)s->worker_words++;else s->exchange_words++;
        f=HW_READ(s,2);note_status(s,f);
    }
    return f;
}
static void *receiver(void *arg){
    Service *s=arg;
    for(;;){
#ifdef SERVICE_FIXTURE
        service_worker_wait();
#endif
        pthread_mutex_lock(&s->lock);
        if(!s->running||s->errors||s->overflow){s->running=0;pthread_mutex_unlock(&s->lock);break;}
        /* Keep status observation and FIFO consumption serialized with TX's
         * status reader, so no clear-on-read error can disappear unnoticed. */
        (void)harvest(s,1);
        pthread_mutex_unlock(&s->lock);
    }
    return NULL;
}
API void *uartlite_service_start(volatile uint32_t *regs,uint32_t capacity){
    Service *s;
    if(!regs||capacity<64||capacity>1048576)return NULL;
    s=calloc(1,sizeof(*s));if(!s)return NULL;
    s->ring=calloc(capacity,sizeof(uint32_t));if(!s->ring){free(s);return NULL;}
    s->arrival_times=calloc(capacity,sizeof(uint64_t));
    if(!s->arrival_times){free(s->ring);free(s);return NULL;}
    s->regs=regs;s->capacity=capacity;s->running=1;
    if(pthread_mutex_init(&s->lock,NULL)){free(s->arrival_times);free(s->ring);free(s);return NULL;}
    if(pthread_create(&s->thread,NULL,receiver,s)){
        pthread_mutex_destroy(&s->lock);free(s->arrival_times);free(s->ring);free(s);return NULL;
    }
    return s;
}
API void uartlite_service_pause(void *ptr){
    Service *s=ptr;if(!s||s->joined)return;
    pthread_mutex_lock(&s->lock);s->running=0;pthread_mutex_unlock(&s->lock);
    pthread_join(s->thread,NULL);s->joined=1;
}
API void uartlite_service_close(void *ptr){
    Service *s=ptr;if(!s)return;uartlite_service_pause(s);
    pthread_mutex_destroy(&s->lock);free(s->arrival_times);free(s->ring);free(s);
}
/* Snapshot preserves the ring; info: pending, actual error status, internal
 * collector fault, running, last actual hardware status. Not a valid frame. */
API uint32_t uartlite_service_snapshot(void *ptr,uint32_t *words,uint32_t cap,uint32_t *info){
    Service *s=ptr;uint32_t n,i;if(!s)return 0;
    pthread_mutex_lock(&s->lock);n=s->count<cap?s->count:cap;
    if(info){info[0]=s->count;info[1]=s->error_status;info[2]=(uint32_t)s->overflow;
        info[3]=(uint32_t)s->running;info[4]=s->last_status;}
    for(i=0;i<n;i++)words[i]=s->ring[(s->head+i)%s->capacity];
    pthread_mutex_unlock(&s->lock);return n;
}
/* Software service telemetry, not physical UART timing. No hardware access. */
API void uartlite_service_metrics(void *ptr,uint64_t *out){
    Service *s=ptr;if(!s||!out)return;
    pthread_mutex_lock(&s->lock);
    out[0]=s->max_service_gap;out[1]=s->worker_words;
    out[2]=s->exchange_words;out[3]=s->service_calls;
    pthread_mutex_unlock(&s->lock);
}
API void uartlite_service_exchange_metrics(void *ptr,uint64_t *out){
    Service *s=ptr;if(!s||!out)return;
    pthread_mutex_lock(&s->lock);
    out[0]=s->tx_words;out[1]=s->first_tx;out[2]=s->last_tx;
    out[3]=s->max_tx_gap;out[4]=s->max_tx_gap_index;
    out[5]=s->worker_words-s->worker_baseline;
    out[6]=s->exchange_words-s->exchange_baseline;out[7]=s->exchange_max_gap;
    pthread_mutex_unlock(&s->lock);
}
uint64_t test_now(void){return service_clock();}
uint64_t service_rx_timestamp(void){return current_service->last_popped_time;}
int service_rx_pending(void){
    Service *s=current_service;int pending;
    pthread_mutex_lock(&s->lock);pending=s->count!=0||(s->last_status&1u)!=0;
    pthread_mutex_unlock(&s->lock);return pending;
}
uint32_t test_read(uint32_t index){
    Service *s=current_service;uint32_t f,w=0xffffffff;int popped=0;
    if(!s)return w;
    pthread_mutex_lock(&s->lock);
    if(index==2){
        f=harvest(s,0);
        /* RX flags describe the software ring. Error/TX flags come from HW. */
        w=(f&0x1cu)|s->errors|(s->count?1u:0u)|(s->count>=16?2u:0u);
        if(s->overflow||(!s->running&&!s->errors))w|=0x100u;
    }else if(index==0&&s->count){
        w=s->ring[s->head];s->last_popped_time=s->arrival_times[s->head];
        s->head=(s->head+1)%s->capacity;s->count--;popped=1;
    }
    pthread_mutex_unlock(&s->lock);
#ifdef SERVICE_FIXTURE
    if(popped)service_after_pop();
#else
    (void)popped;
#endif
    return w;
}
void test_write(uint32_t index,uint32_t value){
    Service *s=current_service;uint64_t now,gap;if(index!=1||!s)return;
    pthread_mutex_lock(&s->lock);
    HW_WRITE(s,1,value);
    now=service_clock();
    if(!s->tx_words)s->first_tx=now;
    else{
        gap=now-s->last_tx;
        if(gap>s->max_tx_gap){s->max_tx_gap=gap;s->max_tx_gap_index=s->tx_words+1;}
    }
    s->last_tx=now;s->tx_words++;
    pthread_mutex_unlock(&s->lock);
}
API int uartlite_service_collect(void *ptr,const uint8_t *tx,uint32_t n,
    int expected,int (*guard)(void),uint8_t *raw,uint32_t cap,
    uint32_t *statuses,uint32_t scap,uint32_t *out,uint64_t timeout,
    uint64_t quiet,uint64_t gap,uint32_t budget,uint32_t frame_limit){
    Service *s=ptr;int result;
    if(!s){memset(out,0,12*sizeof(uint32_t));out[10]=15;return 15;}
    pthread_mutex_lock(&s->lock);
    s->tx_words=s->first_tx=s->last_tx=s->max_tx_gap=s->max_tx_gap_index=0;
    s->exchange_last_service=s->exchange_max_gap=0;
    s->worker_baseline=s->worker_words;s->exchange_baseline=s->exchange_words;
    s->exchange_active=1;
    pthread_mutex_unlock(&s->lock);
    current_service=s;
    result=uartlite_collect(s->regs,tx,n,expected,guard,raw,cap,statuses,scap,
        out,timeout,quiet,gap,budget,frame_limit);
    current_service=NULL;
    pthread_mutex_lock(&s->lock);s->exchange_active=0;pthread_mutex_unlock(&s->lock);
    return result;
}
