/* Software register/scheduled-wire model only; never accesses a device. */
#define NATIVE_TEST
#include "../host/uartlite_native.c"
static uint64_t ticks,origin;
static uint8_t data[4096],written[4096];
static uint32_t length,produced,consumed,txcount,trigger,mode,rxreads;
API void fixture_reset(const uint8_t *p,uint32_t len,uint32_t when,uint32_t how){
    ticks=0;origin=0;length=len;produced=consumed=txcount=rxreads=0;
    trigger=when;mode=how;memcpy(data,p,len);
}
API uint32_t fixture_txcount(void){return txcount;}
API uint32_t fixture_rxreads(void){return rxreads;}
uint64_t test_now(void){return ticks;}
uint32_t test_read(uint32_t index){
    uint32_t flags; ticks+=500;
    if(txcount>=trigger){
        if(!origin)origin=ticks;
        while(produced<length&&ticks-origin>=(uint64_t)produced*43400)produced++;
    }
    if(index==2){
        flags=4|(produced>consumed?1:0)|(produced-consumed>=16?2:0);
        if(mode==1&&consumed>=22)flags=0x27;
        return flags;
    }
    if(index==0&&consumed<produced){
        uint32_t value=data[consumed++];rxreads++;
        return mode==2?value|0x100:value;
    }
    return 0xffffffff;
}
void test_write(uint32_t index,uint32_t value){
    if(index!=1||value>255||txcount>=4096)return;
    written[txcount++]=(uint8_t)value;ticks+=500;
}
