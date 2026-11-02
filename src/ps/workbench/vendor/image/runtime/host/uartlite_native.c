/* Bounded, exclusive UARTLite collector. No reset/IRQ/clock/START commands.
 * REG offsets accessed: RX 0, TX 4, STATUS 8 only. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <stdint.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#define API __declspec(dllexport)
#else
#include <time.h>
#define API
#endif
#ifdef NATIVE_TEST
extern uint64_t test_now(void);
extern uint32_t test_read(uint32_t index);
extern void test_write(uint32_t index, uint32_t value);
#define NOW() test_now()
#define READ(i) test_read(i)
#define WRITE(i,v) test_write(i,v)
#else
static uint64_t now_ns(void) {
#ifdef _WIN32
    LARGE_INTEGER t,f; QueryPerformanceCounter(&t); QueryPerformanceFrequency(&f);
    return (uint64_t)((double)t.QuadPart*1e9/(double)f.QuadPart);
#else
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000000000u+(uint64_t)t.tv_nsec;
#endif
}
#define NOW() now_ns()
#define READ(i) regs[i]
#define WRITE(i,v) (regs[i]=(v))
#endif
#ifndef RX_TIMESTAMP
#define RX_TIMESTAMP() NOW()
#endif
#ifndef RX_DATA_PENDING
#define RX_DATA_PENDING() 0
#endif
static uint16_t crc(const uint8_t *p,uint32_t n) {
    uint16_t c=0xffff; uint32_t i,k;
    for(i=0;i<n;i++){c^=(uint16_t)p[i]<<8;for(k=0;k<8;k++)c=(uint16_t)((c&0x8000)?(c<<1)^0x1021:c<<1);}
    return c;
}
static int notification(int t){return t==0x31||t==0x32||t==0x33||t==0x38;}
/* out: rxlen,txconfirmed,txattempts,statuscount,polls,parsed,frames,badword,
 * replies,last_status,error,guard_calls. Error 0 means complete transport only. */
API int uartlite_collect(volatile uint32_t *regs,const uint8_t *tx,uint32_t n,
    int expected,int (*guard)(void),uint8_t *raw,uint32_t cap,
    uint32_t *statuses,uint32_t scap,uint32_t *out,uint64_t timeout,
    uint64_t quiet,uint64_t gap,uint32_t budget,uint32_t frame_limit) {
    uint64_t start=NOW(),last=start,last_rx=start,t,arrival;
    uint32_t f,w,begin,size,have;int phase=0,e=0;
    memset(out,0,12*sizeof(uint32_t));
    (void)regs;
    if(!raw||!statuses||!cap||!scap||!timeout||!quiet||!gap||!budget||!frame_limit){out[10]=15;return 15;}
    for(;;){
        if(out[4]>=budget){e=10;break;} out[4]++;
        f=READ(2);out[9]=f;
        if(!out[3]||statuses[out[3]-1]!=f){
            if(out[3]>=scap){e=10;break;} statuses[out[3]++]=f;
        }
        if((f&~255u)||((f&12u)==12u)){e=15;break;}
        if(f&0xe0u){e=3;break;}
        t=NOW();if(t-start>=timeout){e=1;break;}
        if(out[0]>out[5]&&!(f&1u)&&!RX_DATA_PENDING()&&t-last_rx>=gap){e=2;break;}
        if(f&1u){
            if(out[0]>=cap){e=11;break;}
            w=READ(0);if(w>255){out[7]=w;e=4;break;}
            arrival=RX_TIMESTAMP();have=out[0]>out[5];
            raw[out[0]++]=(uint8_t)w;
            if(have&&arrival>=last_rx&&arrival-last_rx>=gap){e=2;break;}
            last_rx=arrival;last=NOW();
            begin=out[5];have=out[0]-begin;
            if(raw[begin]!=0xa5||(have>=2&&raw[begin+1]!=0x5a)||(have>=3&&raw[begin+2]!=1)){e=5;break;}
            if(have>=5){
                if(raw[begin+4]>32){e=5;break;}size=raw[begin+4]+7u;
                if(have==size){
                    if(crc(raw+begin+2,size-4)!=(uint16_t)((raw[begin+size-2]<<8)|raw[begin+size-1])){e=6;break;}
                    if(!notification(raw[begin+3])){
                        if(phase==0){e=13;break;}
                        if(raw[begin+3]!=expected){e=7;break;}
                        if(out[1]<n){e=9;break;}
                        if(++out[8]>1){e=8;break;}
                    }
                    if(++out[6]>frame_limit){e=14;break;}out[5]=out[0];
                }
            }
            continue; /* No Python/CRC callback/file IO in this collection loop. */
        }
        if(phase==0){
            if(out[0]!=out[5]||!(f&4u)||RX_DATA_PENDING())continue;
            if(n&&guard){out[11]++;if(guard()){e=12;break;}}
            phase=1;continue; /* Recheck hardware/errors after the guard. */
        }
        if(out[1]<n){
            if(f&8u)continue;
            out[2]++;WRITE(1,tx[out[1]]);out[1]++;last=NOW();continue;
        }
        if((expected<0||out[8]==1)&&out[0]==out[5]&&(f&4u)&&t-last>=quiet)break;
    }
    out[10]=(uint32_t)e;return e;
}
