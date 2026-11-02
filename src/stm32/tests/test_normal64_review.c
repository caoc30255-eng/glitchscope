#include "image_stream.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static img_stream_t s;
static uint32_t now;
static unsigned checks;
static uint8_t request[534], expected[532], observed[532], raw[16384], rebuilt[16384];
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"NORMAL64_REVIEW_FAIL line=%d %s\n",__LINE__,#x);exit(1);}}while(0)
static size_t load(const char *base,const char *name,uint8_t *out,size_t capacity)
{
    char path[1200];FILE *f;size_t n;
    CHECK(snprintf(path,sizeof path,"%s/%s",base,name)>0);
    f=fopen(path,"rb");CHECK(f!=NULL);
    n=fread(out,1u,capacity,f);CHECK(!ferror(f));CHECK(fgetc(f)==EOF);
    fclose(f);return n;
}
static void execute(const uint8_t *frame,size_t n,const uint8_t *reply,size_t reply_n)
{
    size_t i;img_event_t e;
    CHECK(s.state==IS_SEARCH);
    for(i=0;i<n;i++) {
        e.us=now+(uint32_t)(i*10u);e.data=frame[i];
        e.flags=0u;e.has_byte=1u;e.reserved=0u;img_stream_feed(&s,e);
    }
    now+=(uint32_t)((n-1u)*10u+100u);
    img_stream_poll(&s,now,1u);
    CHECK(s.state==IS_TX);CHECK(s.tx_len==reply_n);
    CHECK(memcmp(s.tx,reply,reply_n)==0);
    memcpy(observed,s.tx,reply_n);
    now+=(uint32_t)(reply_n*10u);
    img_stream_tx_complete(&s,now); /* Explicit software TC fixture only. */
    now+=100u;img_stream_poll(&s,now,1u);now+=10u;
}
int main(int argc,char **argv)
{
    size_t n,r;unsigned i;char name[100];
    CHECK(argc==2);CHECK(load(argv[1],"original.raw",raw,sizeof raw)==sizeof raw);
    img_stream_init(&s,0u);now=100u;img_stream_poll(&s,now,1u);now+=10u;
    n=load(argv[1],"config.bin",request,sizeof request);
    r=load(argv[1],"config_ack.bin",expected,sizeof expected);execute(request,n,expected,r);
    CHECK(s.config.valid);CHECK(s.config.item_total==64u);
    for(i=0;i<64u;i++) {
        (void)snprintf(name,sizeof name,"items/item_%03u_request.bin",i);
        n=load(argv[1],name,request,sizeof request);
        (void)snprintf(name,sizeof name,"reports/item_%03u_report.bin",i);
        r=load(argv[1],name,expected,sizeof expected);
        CHECK(n==278u && r==276u);execute(request,n,expected,r);
        memcpy(rebuilt+i*256u,observed+18u,256u);
    }
    CHECK(memcmp(rebuilt,raw,sizeof raw)==0);CHECK(s.diag.frames_ok==64u);
    n=load(argv[1],"cleanup.bin",request,sizeof request);
    r=load(argv[1],"cleanup_ack.bin",expected,sizeof expected);execute(request,n,expected,r);
    CHECK(!s.config.valid);CHECK(s.diag.tx_done==66u);
    printf("STM_V03_NORMAL64_HOST_PASS items=64 tx_done=66 raw_bytes=16384 checks=%u (software TC/quiet fixtures only)\n",checks);
    return 0;
}
