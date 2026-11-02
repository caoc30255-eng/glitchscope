#ifndef IMAGE_STREAM_H
#define IMAGE_STREAM_H
#include "image_protocol.h"

#define IMG_IDLE_US 100u
#define IMG_INTERBYTE_US 2000u
/* Local resource watchdog, NOT the host's trusted 30000 us deadline. */
#define IMG_LOCAL_WATCHDOG_US 20000u
#define IMG_CAPTURE_CAP 608u
#define IMG_RING_CAP 1024u

typedef struct {
    uint32_t us;
    uint8_t data, flags, has_byte, reserved;
} img_event_t;
typedef enum { IS_DRAIN, IS_SEARCH, IS_RX, IS_BOUNDARY, IS_TX } img_state_t;
typedef enum {
    IF_NONE, IF_HEADER, IF_CONFIG, IF_CRC, IF_UART, IF_LENGTH,
    IF_TIMEOUT, IF_OVERFLOW, IF_BUSY, IF_WATCHDOG, IF_TX_TIMEOUT,
    IF_CAPTURE_FULL, IF_COUNT
} img_fault_t;
typedef struct {
    uint32_t counts[IF_COUNT];
    uint32_t first_us;
    uint16_t first_offset;
    uint8_t first_reason, first_flags;
    uint32_t frames_ok, reports, tx_done, extra_bytes, orphan_events;
} img_diag_t;
typedef struct {
    img_config_t config;
    img_diag_t diag;
    img_event_t capture[IMG_CAPTURE_CAP];
    uint8_t frame[IMG_MAX_REQUEST_FRAME];
    uint8_t tx[IMG_MAX_REPORT_FRAME];
    uint32_t last_activity, started;
    uint16_t used, expected, tx_len, capture_count;
    uint8_t flags, extra, evidence_lost, clear_on_tc;
    img_state_t state;
} img_stream_t;
typedef struct {
    img_event_t events[IMG_RING_CAP];
    volatile uint16_t head, tail, high_water;
    volatile uint32_t overflow;
} img_ring_t;

void img_stream_init(img_stream_t *s, uint32_t now);
void img_stream_feed(img_stream_t *s, img_event_t event);
/* Drain older events first. quiet requires the hardware sticky-edge latch,
 * GPIO, USART pending bits and event ring all to be clear/high. */
void img_stream_poll(img_stream_t *s, uint32_t now, uint8_t quiet);
/* Physical falling activity; not a UART byte/error. Never synthesize ORE. */
void img_stream_rx_activity(img_stream_t *s, uint32_t observed_us);
/* Cancel a queued report before its FIRST DR write, not after transmission. */
void img_stream_tx_inhibited(img_stream_t *s, uint32_t now);
void img_stream_overflow(img_stream_t *s, uint32_t now);
void img_stream_tx_complete(img_stream_t *s, uint32_t now);
void img_stream_tx_failed(img_stream_t *s, uint32_t now);
/* Single producer ISR / single consumer main; publication barriers supplied by HAL. */
uint8_t img_ring_push(img_ring_t *r, img_event_t e);
uint8_t img_ring_pop(img_ring_t *r, img_event_t *e);
#endif
