#include "image_stream.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Register-semantics model only: not execution of MCU peripherals or NVIC. */
typedef struct { uint32_t pr; } latch_t;
#define LINE10 (1u << 10)
static unsigned checks;
static img_stream_t s;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"ACTIVITY_FAIL line=%d %s\n",__LINE__,#x); exit(1); } } while(0)
static void falling(latch_t *l,uint16_t time)
{
    (void)time; l->pr |= LINE10;
}
/* EXTI PR read -> W1C line10. Edges before W1C can coalesce, but activity=true
 * restarts the window AFTER W1C. An edge after W1C must remain pending. */
static uint8_t take(latch_t *l,uint8_t edge_after_clear)
{
    uint32_t flags=l->pr & LINE10;
    if(!flags) return 0u;
    l->pr &= ~LINE10;
    if(edge_after_clear) falling(l,97u);
    return 1u;
}
static void boundary(uint32_t last)
{
    /* Construct a real valid configured ITEM via the production protocol API. */
    uint8_t *p=s.frame;
    img_stream_init(&s,last);
    s.config.valid=1u; s.config.run_id=7u; s.config.image_id=1u;
    s.config.total_bytes=1u; s.config.width=s.config.height=1u;
    s.config.item_total=s.config.chunk_size=1u;
    memset(p,0,23u); p[0]=0x55u; p[1]=0xaau; p[2]=2u;
    img_write_be32(p+3u,7u); p[7]=1u;
    img_write_be16(p+12u,1u); img_write_be16(p+18u,1u); p[20]=0x6cu;
    s.config.item_crc[0]=img_crc16(p+20u,1u);
    img_write_be16(p+16u,s.config.item_crc[0]);
    img_write_be16(p+21u,img_crc16(p+2u,19u));
    s.used=s.expected=23u; s.started=last-220u; s.last_activity=last;
    s.state=IS_BOUNDARY;
}
static void service(latch_t *l,uint32_t now,uint8_t pin_high)
{
    uint8_t activity=take(l,0u);
    if(activity) img_stream_rx_activity(&s,now);
    img_stream_poll(&s,now,(uint8_t)(!activity && !(l->pr & LINE10) && pin_high));
}
int main(void)
{
    latch_t l; img_event_t e; uint32_t d;
    memset(&l,0,sizeof l);
    /* Control: the v0.2 single-point scheme misses the 95..96 us pulse. */
    boundary(1000u); img_stream_poll(&s,1094u,1u);
    img_stream_poll(&s,1100u,1u); CHECK(s.state==IS_TX); CHECK(s.tx[15]==IMG_STATUS_OK);
    /* Reviewer counterexample: start low 95, high at 96, RXNE only at 105.
     * Hardware PR remains set while GPIO and USART SR look idle at 100. */
    boundary(1000u); memset(&l,0,sizeof l); service(&l,1094u,1u);
    falling(&l,1095u); service(&l,1100u,1u);
    CHECK(s.state==IS_BOUNDARY); CHECK(s.extra); CHECK(!s.tx_len); CHECK(!s.flags);
    e.us=1105u; e.data=0xffu; e.has_byte=1u; e.flags=e.reserved=0u;
    img_stream_feed(&s,e); CHECK(s.state==IS_BOUNDARY); CHECK(s.diag.extra_bytes==1u);
    service(&l,1205u,1u); CHECK(s.state==IS_TX); CHECK(s.tx[15]==IMG_STATUS_LEN_ERR);
    CHECK(s.tx[14]==0u); /* A physical edge is not a fabricated USART error. */
    /* If ISR consumes the edge before main at 110, queued RXNE still blocks
     * closure. Never infer start-bit time from its later completion time. */
    boundary(1000u); falling(&l,1095u); CHECK(take(&l,0u));
    e.us=1105u; img_stream_feed(&s,e); CHECK(s.state==IS_BOUNDARY);
    img_stream_poll(&s,1205u,1u); CHECK(s.tx[15]==IMG_STATUS_LEN_ERR);
    /* Single edge, coalesced edges, boundary and wrap are conservative. */
    for(d=99u;d<=101u;d++) {
        boundary(1000u); memset(&l,0,sizeof l); falling(&l,(uint16_t)(1000u+d));
        service(&l,1000u+d,1u); CHECK(s.state==IS_BOUNDARY); CHECK(s.extra);
    }
    boundary(1000u); memset(&l,0,sizeof l); falling(&l,1095u); falling(&l,1096u);
    CHECK(l.pr & LINE10); service(&l,1100u,1u);
    CHECK(s.extra); CHECK(!s.flags); CHECK(s.state==IS_BOUNDARY);
    memset(&l,0,sizeof l); falling(&l,95u); CHECK(take(&l,1u));
    CHECK(l.pr & LINE10); CHECK(take(&l,0u)); CHECK(!l.pr);
    /* Sticky PR does not depend on a wrapping timestamp or service cadence. */
    boundary(1000u); memset(&l,0,sizeof l); falling(&l,65535u);
    service(&l,1500u,1u); CHECK(s.extra); CHECK(s.last_activity==1500u);
    boundary(0xfffffff0u); memset(&l,0,sizeof l); falling(&l,1u);
    service(&l,84u,1u); CHECK(s.state==IS_BOUNDARY); CHECK(s.extra);
    /* Recheck cancellation before first write cannot claim TC or cleanup. */
    boundary(1000u); img_stream_poll(&s,1100u,1u); CHECK(s.state==IS_TX);
    CHECK(!s.diag.frames_ok); s.clear_on_tc=1u;
    img_stream_tx_inhibited(&s,1101u); CHECK(s.state==IS_DRAIN);
    CHECK(s.config.valid); CHECK(!s.clear_on_tc); CHECK(!s.diag.tx_done);
    CHECK(!s.diag.frames_ok); CHECK(s.diag.counts[IF_BUSY]==1u);
    /* RX activity also restarts boot/drain idle; no per-edge IRQ is needed. */
    img_stream_init(&s,0u); memset(&l,0,sizeof l); falling(&l,95u);
    service(&l,100u,1u); CHECK(s.state==IS_DRAIN);
    service(&l,199u,1u); CHECK(s.state==IS_DRAIN);
    service(&l,200u,1u); CHECK(s.state==IS_SEARCH);
    printf("RX_ACTIVITY_MODEL_PASS checks=%u (software latch model only)\n",checks);
    return 0;
}
