#include "image_stream.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static img_stream_t s;
static img_ring_t ring;
static uint8_t cfg[IMG_MAX_CONFIG_FRAME], req[IMG_MAX_REQUEST_FRAME];
static uint8_t ack[12], report[IMG_MAX_REPORT_FRAME], cleanup[12], cleanup_ack[12];
static size_t cfg_n, req_n, report_n;
static unsigned checks;
static const char *vector_dir;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
static size_t load(const char *dir, const char *name, uint8_t *out, size_t cap)
{
    char path[1024]; FILE *f; size_t n;
    (void)snprintf(path, sizeof path, "%s/%s", dir, name);
    f = fopen(path, "rb"); if (!f) { perror(path); exit(2); }
    n = fread(out, 1u, cap, f); CHECK(!ferror(f)); CHECK(fgetc(f) == EOF);
    fclose(f); return n;
}
static void event(uint32_t t, uint8_t data, uint8_t flags, uint8_t has)
{
    img_event_t e; e.us=t; e.data=data; e.flags=flags; e.has_byte=has; e.reserved=0u;
    img_stream_feed(&s,e);
}
static uint32_t frame(const uint8_t *p, size_t n, uint32_t t)
{
    size_t i; for(i=0u;i<n;i++) event(t+(uint32_t)i*10u,p[i],0u,1u);
    return t+(uint32_t)(n-1u)*10u;
}
static void boot(uint32_t t)
{
    img_stream_init(&s,t); img_stream_poll(&s,t+99u,1u); CHECK(s.state==IS_DRAIN);
    img_stream_poll(&s,t+100u,1u); CHECK(s.state==IS_SEARCH);
}
static void configure(void)
{
    uint32_t end;
    boot(0u); end=frame(cfg,cfg_n,200u);
    CHECK(s.state==IS_BOUNDARY); img_stream_poll(&s,end+99u,1u);
    CHECK(s.state==IS_BOUNDARY); CHECK(!s.config.valid);
    img_stream_poll(&s,end+100u,1u); CHECK(s.state==IS_TX);
    CHECK(s.tx_len==12u); CHECK(memcmp(s.tx,ack,12u)==0);
    img_stream_tx_complete(&s,end+220u);
    img_stream_poll(&s,end+320u,1u); CHECK(s.state==IS_SEARCH); CHECK(s.config.valid);
}
static uint32_t item_start(void) { return 5000u; }
static void normal_and_busy(void)
{
    uint32_t end, done; uint8_t saved[IMG_MAX_REPORT_FRAME];
    configure(); end=frame(req,req_n,item_start());
    CHECK(s.state==IS_BOUNDARY); CHECK(s.used==req_n);
    img_stream_poll(&s,end+100u,1u); CHECK(s.state==IS_TX);
    CHECK(s.tx_len==report_n); CHECK(memcmp(s.tx,report,report_n)==0);
    {
        char path[1024]; FILE *out;
        (void)snprintf(path,sizeof path,"%s/actual_report_software.bin",vector_dir);
        out=fopen(path,"wb"); CHECK(out!=NULL);
        CHECK(fwrite(s.tx,1u,s.tx_len,out)==s.tx_len); CHECK(fclose(out)==0);
    }
    memcpy(saved,s.tx,s.tx_len);
    /* A management frame during report TX must not clear config or TX bytes. */
    (void)frame(cleanup,12u,end+110u);
    CHECK(s.config.valid); CHECK(memcmp(saved,s.tx,s.tx_len)==0);
    CHECK(s.diag.counts[IF_BUSY]==12u);
    done=end+1000u; img_stream_tx_complete(&s,done);
    CHECK(s.state==IS_DRAIN); img_stream_poll(&s,done+100u,1u);
    end=frame(cleanup,12u,done+200u); img_stream_poll(&s,end+100u,1u);
    CHECK(s.state==IS_TX); CHECK(s.config.valid); CHECK(s.tx_len==12u);
    CHECK(memcmp(s.tx,cleanup_ack,12u)==0);
    img_stream_tx_complete(&s,end+230u); CHECK(!s.config.valid);
}
static void guard_tests(void)
{
    uint32_t end; unsigned d;
    for(d=99u;d<=101u;d++) {
        configure(); end=frame(req,req_n,item_start());
        event(end+d,0x99u,0u,1u);
        if(d<=101u) {
            CHECK(s.state==IS_BOUNDARY); CHECK(s.extra);
            img_stream_poll(&s,end+d+100u,1u); CHECK(s.state==IS_TX);
            CHECK(s.tx[15]==IMG_STATUS_LEN_ERR);
            CHECK(img_read_be16(s.tx+16u)==req_n-22u);
        }
    }
    configure(); end=frame(req,req_n,item_start());
    event(end+100u,0u,2u,0u); CHECK(s.used==req_n);
    img_stream_poll(&s,end+200u,1u); CHECK(s.tx[15]==IMG_STATUS_UART_ERR);
    CHECK(s.tx[14]==2u); CHECK(s.capture[s.capture_count-1u].has_byte==0u);
    /* Low PA10 delays idle closure, local watchdog bounds sustained low. */
    configure(); end=frame(req,req_n,item_start());
    img_stream_poll(&s,end+100u,0u); CHECK(s.state==IS_BOUNDARY);
    img_stream_poll(&s,end+199u,1u); CHECK(s.state==IS_BOUNDARY);
    img_stream_poll(&s,end+200u,1u); CHECK(s.state==IS_TX);
    CHECK(s.tx[15]==IMG_STATUS_LEN_ERR);
}
static void failures(void)
{
    uint32_t end; uint8_t altered[IMG_MAX_REQUEST_FRAME]; unsigned flag;
    configure(); memcpy(altered,req,req_n); altered[req_n-1u]^=1u;
    end=frame(altered,req_n,item_start()); img_stream_poll(&s,end+100u,1u);
    CHECK(s.tx[15]==IMG_STATUS_REQ_CRC_ERR); CHECK(memcmp(s.tx+18u,req+20u,req_n-22u)==0);
    configure(); memcpy(altered,req,req_n); altered[20]^=1u;
    img_write_be16(altered+req_n-2u,img_crc16(altered+2u,req_n-4u));
    end=frame(altered,req_n,item_start()); img_stream_poll(&s,end+100u,1u);
    CHECK(s.tx[15]==IMG_STATUS_REQ_CRC_ERR);
    for(flag=1u;flag<=8u;flag*=2u) {
        configure(); end=frame(req,req_n,item_start()); event(end+50u,0u,(uint8_t)flag,0u);
        img_stream_poll(&s,end+150u,1u);
        if(flag==8u) { CHECK(s.state==IS_DRAIN); CHECK(s.tx_len==0u); }
        else { CHECK(s.state==IS_TX); CHECK(s.tx[15]==IMG_STATUS_UART_ERR); CHECK(s.tx[14]==flag); }
    }
    configure(); end=frame(altered,req_n,item_start());
    event(end+50u,7u,7u,1u); img_stream_poll(&s,end+150u,1u);
    CHECK(s.tx[15]==IMG_STATUS_UART_ERR); CHECK(s.extra); CHECK(s.diag.counts[IF_CRC]);
    CHECK(s.diag.counts[IF_UART]); CHECK(s.diag.counts[IF_LENGTH]);
    configure(); end=frame(req,req_n-1u,item_start());
    img_stream_poll(&s,end+1999u,1u); CHECK(s.state==IS_RX);
    event(end+2000u,0x55u,0u,1u); CHECK(s.state==IS_DRAIN); CHECK(!s.tx_len);
    CHECK(s.diag.counts[IF_TIMEOUT]==1u); CHECK(s.capture_count==req_n);
    configure(); end=frame(req,20u,item_start());
    img_stream_poll(&s,end+2000u,1u); CHECK(s.state==IS_TX);
    CHECK(s.tx_len==20u); CHECK(img_read_be16(s.tx+16u)==0u);
    CHECK(s.tx[15]==IMG_STATUS_LEN_ERR);
    /* Oversized header, wrong session and unconfigured request: no guessed identity. */
    configure(); memcpy(altered,req,req_n); img_write_be16(altered+18u,513u);
    end=frame(altered,20u,item_start()); CHECK(s.state==IS_DRAIN); CHECK(!s.tx_len);
    configure(); memcpy(altered,req,req_n); altered[3]^=1u;
    end=frame(altered,req_n,item_start()); img_stream_poll(&s,end+100u,1u);
    CHECK(s.state==IS_DRAIN); CHECK(s.diag.counts[IF_CONFIG]);
    boot(0u); end=frame(req,req_n,200u); img_stream_poll(&s,end+100u,1u);
    CHECK(s.state==IS_DRAIN); CHECK(!s.tx_len);
    /* Corrupt CONFIG cannot replace old configuration. */
    configure(); memcpy(altered,cfg,cfg_n); altered[cfg_n-1u]^=1u;
    end=frame(altered,cfg_n,item_start()); img_stream_poll(&s,end+100u,1u);
    CHECK(s.config.valid); CHECK(s.state==IS_DRAIN);
    configure(); end=frame(req,req_n,item_start()); img_stream_overflow(&s,end+10u);
    CHECK(s.state==IS_DRAIN); CHECK(s.flags==0u); CHECK(s.diag.counts[IF_OVERFLOW]);
    configure(); end=frame(req,req_n,item_start());
    img_stream_poll(&s,item_start()+IMG_LOCAL_WATCHDOG_US,0u);
    CHECK(s.state==IS_DRAIN); CHECK(s.diag.counts[IF_WATCHDOG]);
    /* Error-only activities exhaust bounded capture storage, suppress report. */
    configure(); end=frame(req,req_n,item_start());
    for(flag=0u;flag<IMG_CAPTURE_CAP;flag++) event(end+1u+flag,0u,1u,0u);
    img_stream_poll(&s,end+IMG_CAPTURE_CAP+100u,1u);
    CHECK(s.state==IS_DRAIN); CHECK(s.evidence_lost); CHECK(s.diag.counts[IF_CAPTURE_FULL]);
    /* Idempotent CONFIG preserves diagnostics; rejected management bytes do not
     * generate management ACKs when received inside an active ITEM. */
    configure(); s.diag.counts[IF_CRC]=9u;
    end=frame(cfg,cfg_n,item_start()); img_stream_poll(&s,end+100u,1u);
    CHECK(s.state==IS_TX); CHECK(s.diag.counts[IF_CRC]==9u);
    CHECK(memcmp(s.tx,ack,12u)==0);
    configure(); end=frame(req,req_n,item_start());
    end=frame(cleanup,12u,end+10u); img_stream_poll(&s,end+100u,1u);
    CHECK(s.state==IS_TX); CHECK(s.tx[1]==0xbbu); CHECK(s.tx[15]==IMG_STATUS_LEN_ERR);
    CHECK(s.config.valid);
    configure(); end=frame(cleanup,12u,item_start()); img_stream_poll(&s,end+100u,1u);
    img_stream_tx_failed(&s,end+101u); CHECK(s.config.valid);
    CHECK(s.diag.counts[IF_TX_TIMEOUT]);
    /* Reset invalidates configuration and must requalify boot idle. */
    img_stream_init(&s,30000u); CHECK(!s.config.valid); CHECK(s.state==IS_DRAIN);
    img_stream_poll(&s,30100u,0u); CHECK(s.state==IS_DRAIN);
    img_stream_poll(&s,30199u,1u); CHECK(s.state==IS_DRAIN);
    img_stream_poll(&s,30200u,1u); CHECK(s.state==IS_SEARCH);
}
static void ring_and_wrap(void)
{
    unsigned i; img_event_t a,b; uint32_t end;
    memset(&ring,0,sizeof ring); a.us=7u; a.data=0u; a.flags=8u; a.has_byte=0u; a.reserved=0u;
    for(i=0u;i<IMG_RING_CAP-1u;i++) { a.us=i; CHECK(img_ring_push(&ring,a)); }
    CHECK(!img_ring_push(&ring,a)); CHECK(ring.overflow==1u); CHECK(ring.high_water==1023u);
    for(i=0u;i<IMG_RING_CAP-1u;i++) { CHECK(img_ring_pop(&ring,&b)); CHECK(b.us==i); CHECK(!b.has_byte); }
    CHECK(!img_ring_pop(&ring,&b));
    for(i=0u;i<3000u;i++) { a.us=i; CHECK(img_ring_push(&ring,a)); CHECK(img_ring_pop(&ring,&b)); CHECK(b.us==i); }
    boot(0xfffffff0u); end=frame(cfg,cfg_n,200u);
    img_stream_poll(&s,end+100u,1u); CHECK(s.state==IS_TX);
    CHECK(sizeof(img_event_t)==8u); CHECK(sizeof(img_stream_t)+sizeof(img_ring_t)+2048u<20480u);
}
static void payload_markers(void)
{
    uint8_t old_cfg[IMG_MAX_CONFIG_FRAME], altered[IMG_MAX_REQUEST_FRAME];
    static const uint8_t markers[]={0x55u,0xaau,0x55u,0xbbu,0xa6u,0x69u};
    uint32_t end; uint16_t crc,index; size_t n;
    if(req_n-22u<sizeof markers) return;
    memcpy(old_cfg,cfg,cfg_n); memcpy(altered,req,req_n);
    memcpy(altered+20u,markers,sizeof markers);
    crc=img_crc16(altered+20u,req_n-22u);
    img_write_be16(altered+16u,crc);
    img_write_be16(altered+req_n-2u,img_crc16(altered+2u,req_n-4u));
    index=img_read_be16(req+10u);
    img_write_be16(cfg+54u+2u*index,crc);
    img_write_be16(cfg+cfg_n-2u,img_crc16(cfg+2u,cfg_n-4u));
    configure(); end=frame(altered,req_n,item_start()); img_stream_poll(&s,end+100u,1u);
    CHECK(s.state==IS_TX); CHECK(s.tx[15]==IMG_STATUS_OK);
    CHECK(memcmp(s.tx+18u,altered+20u,req_n-22u)==0);
    /* Frozen-buffer capture timestamps correspond to event order. */
    for(n=1u;n<s.capture_count;n++) CHECK(s.capture[n].us-s.capture[n-1u].us==10u);
    memcpy(cfg,old_cfg,cfg_n);
}
int main(int argc,char **argv)
{
    int i;
    if(argc<2) return 2;
    for(i=1;i<argc;i++) {
        vector_dir=argv[i];
        cfg_n=load(argv[i],"config.bin",cfg,sizeof cfg);
        req_n=load(argv[i],"request.bin",req,sizeof req);
        report_n=load(argv[i],"expected_report.bin",report,sizeof report);
        CHECK(load(argv[i],"config_ack.bin",ack,sizeof ack)==12u);
        CHECK(load(argv[i],"cleanup.bin",cleanup,sizeof cleanup)==12u);
        CHECK(load(argv[i],"cleanup_ack.bin",cleanup_ack,sizeof cleanup_ack)==12u);
        normal_and_busy(); guard_tests(); failures(); ring_and_wrap(); payload_markers();
    }
    printf("STREAM_OFFLINE_PASS checks=%u vectors=%d stream_bytes=%lu ring_bytes=%lu\n",
        checks,argc-1,(unsigned long)sizeof s,(unsigned long)sizeof ring);
    return 0;
}
