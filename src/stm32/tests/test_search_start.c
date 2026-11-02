#include "image_stream.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static img_stream_t s;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)){fprintf(stderr,"SEARCH_START_FAIL line=%d %s state=%u orphan=%lu used=%u\n",__LINE__,#x,(unsigned)s.state,(unsigned long)s.diag.orphan_events,s.used);exit(1);} } while(0)
static void feed(uint32_t t,uint8_t b,uint8_t flags,uint8_t has){
    img_event_t e;e.us=t;e.data=b;e.flags=flags;e.has_byte=has;e.reserved=0;
    img_stream_feed(&s,e);
}
int main(int argc,char **argv){
    uint8_t cfg[184];size_t n,i;FILE *f;uint32_t end;
    if(argc!=2&&argc!=3)return 2;
    f=fopen(argv[1],"rb");if(!f)return 2;
    n=fread(cfg,1,sizeof cfg,f);CHECK(!ferror(f));CHECK(fgetc(f)==EOF);fclose(f);
    CHECK(n>=58&&cfg[0]==0x55&&cfg[1]==0xcc&&cfg[2]==2);
    /* Startup still requires a full, hardware-qualified idle interval. */
    img_stream_init(&s,0);img_stream_poll(&s,99,1);CHECK(s.state==IS_DRAIN);
    img_stream_poll(&s,100,1);CHECK(s.state==IS_SEARCH);
    /* A real start bit appears before RXNE. It must not revoke idle credit
     * already earned in SEARCH. Both sticky activity and pin-low are modeled. */
    img_stream_rx_activity(&s,190);img_stream_poll(&s,191,0);
    if(argc==3&&strcmp(argv[2],"--observe-old")==0){
        for(i=0;i<n;i++)feed(200+(uint32_t)i*10,cfg[i],0,1);
        end=200+(uint32_t)(n-1)*10;img_stream_poll(&s,end+100,1);
        printf("OLD_COUNTEREXAMPLE state=%u orphan=%lu capture=%u used=%u config_valid=%u reports=%lu tx_done=%lu\n",
            (unsigned)s.state,(unsigned long)s.diag.orphan_events,s.capture_count,s.used,
            s.config.valid,(unsigned long)s.diag.reports,(unsigned long)s.diag.tx_done);
        return (s.state==IS_SEARCH&&s.diag.orphan_events==n&&s.capture_count==n&&
            !s.used&&!s.config.valid&&!s.diag.reports&&!s.diag.tx_done)?0:1;
    }
    CHECK(s.state==IS_SEARCH);
    for(i=0;i<n;i++){
        if(i)img_stream_poll(&s,195+(uint32_t)i*10,0);
        feed(200+(uint32_t)i*10,cfg[i],0,1);
    }
    end=200+(uint32_t)(n-1)*10;
    CHECK(s.state==IS_BOUNDARY);CHECK(s.used==n);CHECK(!s.diag.orphan_events);
    img_stream_poll(&s,end+99,1);CHECK(s.state==IS_BOUNDARY);
    img_stream_poll(&s,end+100,1);CHECK(s.state==IS_TX);
    CHECK(s.config.valid);CHECK(s.tx_len==12);CHECK(s.diag.reports==1);
    CHECK(!s.diag.frames_ok&&!s.diag.tx_done);
    /* frames_ok counts successful ITEM reports only, not CONFIG_ACK. */
    img_stream_tx_complete(&s,end+220);CHECK(!s.diag.frames_ok&&s.diag.tx_done==1);
    /* No initial idle: all incoming bytes remain diagnostic orphans. */
    img_stream_init(&s,0);img_stream_poll(&s,90,0);
    for(i=0;i<n;i++)feed(100+(uint32_t)i*10,cfg[i],0,1);
    CHECK(s.state==IS_DRAIN);CHECK(s.diag.orphan_events==n);CHECK(!s.config.valid);
    /* Start activity is not a fabricated valid byte, frame or UART error. */
    img_stream_init(&s,0);img_stream_poll(&s,100,1);
    for(i=0;i<100;i++){img_stream_rx_activity(&s,200+(uint32_t)i);img_stream_poll(&s,200+(uint32_t)i,0);}
    CHECK(s.state==IS_SEARCH);CHECK(!s.used&&!s.tx_len&&!s.config.valid);
    CHECK(!s.diag.frames_ok&&!s.diag.reports&&!s.flags);
    /* Genuine error-only observation must still reject admission. */
    feed(400,0,2,0);CHECK(s.state==IS_DRAIN);CHECK(s.diag.counts[IF_UART]==1);
    CHECK(!s.used&&!s.tx_len&&!s.config.valid);
    /* Waiting in SEARCH does not weaken bad SOF/header rejection. */
    img_stream_init(&s,0);img_stream_poll(&s,100,1);img_stream_poll(&s,190,0);
    feed(200,0x55,0,1);feed(210,0x99,0,1);
    CHECK(s.diag.counts[IF_HEADER]==1);CHECK(!s.config.valid&&!s.tx_len);
    printf("SEARCH_START_REGRESSION_PASS checks=%u config_bytes=%u (software model, no MCU)\n",checks,(unsigned)n);
    return 0;
}
