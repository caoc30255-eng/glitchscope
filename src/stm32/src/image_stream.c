#include "image_stream.h"
#include <string.h>

#if defined(__arm__) || defined(__thumb__)
#define EVENT_BARRIER() __asm__ volatile ("dmb" ::: "memory")
#else
#define EVENT_BARRIER() __asm__ volatile ("" ::: "memory")
#endif

static uint32_t age(uint32_t now, uint32_t then) { return now - then; }
static void fault(img_stream_t *s, img_fault_t why, uint32_t now)
{
    s->diag.counts[why]++;
    if (s->diag.first_reason == IF_NONE) {
        s->diag.first_reason = (uint8_t)why;
        s->diag.first_us = now;
        s->diag.first_offset = s->used;
        s->diag.first_flags = s->flags;
    }
}
static void drain(img_stream_t *s, uint32_t now)
{
    s->state = IS_DRAIN;
    s->last_activity = now;
    s->tx_len = 0u;
}
static void save_event(img_stream_t *s, img_event_t e)
{
    if (s->capture_count < IMG_CAPTURE_CAP) s->capture[s->capture_count++] = e;
    else if (!s->evidence_lost) {
        s->evidence_lost = 1u;
        fault(s, IF_CAPTURE_FULL, e.us);
    }
}
void img_stream_init(img_stream_t *s, uint32_t now)
{
    memset(s, 0, sizeof *s);
    s->state = IS_DRAIN; /* Boot must observe an idle window before accepting SOF. */
    s->last_activity = now;
}
static void queue(img_stream_t *s, size_t n)
{
    s->tx_len = (uint16_t)n;
    s->state = IS_TX;
    s->diag.reports++;
}
static void close_frame(img_stream_t *s, uint32_t now)
{
    img_item_t item;
    img_parse_result_t result;
    size_t n;
    if (s->evidence_lost || (s->flags & 8u) != 0u) {
        /* ORE / lost events can shift payload positions: never invent a report. */
        drain(s, now);
        return;
    }
    if (s->frame[1] == 0xaau) {
        result = img_parse_item(s->frame, s->used, &s->config, &item);
        if (!item.safe_candidate) {
            fault(s, result == IMG_PARSE_CONFIG ? IF_CONFIG : IF_HEADER, now);
            drain(s, now);
            return;
        }
        if (result != IMG_PARSE_OK) fault(s, IF_CRC, now);
        n = img_build_report(&item, item.payload, item.payload_len, s->flags,
                             s->extra, s->tx, sizeof s->tx);
        if (n != 0u) {
            queue(s, n);
            return;
        }
    } else if (s->flags == 0u && s->extra == 0u) {
        if (s->frame[1] == 0xccu) {
            result = img_parse_config(s->frame, s->used, &s->config);
            if (result == IMG_PARSE_OK) {
                queue(s, img_build_config_ack(&s->config, s->tx, sizeof s->tx));
                return;
            }
        } else {
            result = img_parse_cleanup(s->frame, s->used, &s->config);
            if (result == IMG_PARSE_OK) {
                s->clear_on_tc = 1u;
                queue(s, img_build_cleanup_ack(&s->config, s->tx, sizeof s->tx));
                return;
            }
        }
        fault(s, result == IMG_PARSE_FRAME_CRC ? IF_CRC : IF_CONFIG, now);
    }
    drain(s, now);
}
/* Event priority at exact boundary: an incoming event prevents idle closure.
 * Only explicit hardware-qualified quiet polling may close a frame. A late
 * RXNE timestamp does not prove the start bit arrived after the idle window.
 * Incomplete-frame timeout at its exact limit wins before an incoming byte.
 * Wrap-safe differences require successive calls < 2^31 us apart. */
static void advance(img_stream_t *s, uint32_t now, uint8_t has_event)
{
    if (s->state == IS_RX || s->state == IS_BOUNDARY) {
        if (age(now, s->started) >= IMG_LOCAL_WATCHDOG_US) {
            fault(s, IF_WATCHDOG, now); drain(s, now); return;
        }
    }
    if (s->state == IS_RX && age(now, s->last_activity) >= IMG_INTERBYTE_US) {
        img_item_t header;
        size_t n;
        fault(s, IF_TIMEOUT, now);
        /* Exactly a complete header and no body bytes: M=0 is unambiguous.
         * An incoming event at the timeout boundary belongs to orphan/TX. */
        if (s->used == 20u && s->frame[1] == 0xaau && !s->evidence_lost &&
            (s->flags & 8u) == 0u &&
            img_parse_item_header(s->frame, s->used, &s->config, &header) == IMG_PARSE_OK) {
            n = img_build_report(&header, NULL, 0u, s->flags, 1u, s->tx, sizeof s->tx);
            if (n) { queue(s, n); return; }
        }
        /* Truncation cannot reliably distinguish missing payload from tail CRC.
         * Keep capture for diagnosis, do not construct partial data by guessing. */
        drain(s, now);
    } else if (s->state == IS_BOUNDARY &&
               age(now, s->last_activity) >= IMG_IDLE_US &&
               !has_event) {
        close_frame(s, now);
    } else if (s->state == IS_DRAIN && age(now, s->last_activity) >= IMG_IDLE_US &&
               !has_event) {
        s->state = IS_SEARCH;
        s->used = 0u;
    }
}
void img_stream_feed(img_stream_t *s, img_event_t e)
{
    if (!e.has_byte && e.flags == 0u) return;
    advance(s, e.us, 1u);
    if (s->state == IS_TX) {
        save_event(s, e);
        s->diag.orphan_events++;
        fault(s, IF_BUSY, e.us);
        s->last_activity = e.us;
        return;
    }
    if (s->state == IS_DRAIN) {
        save_event(s, e);
        s->diag.orphan_events++;
        s->last_activity = e.us;
        return;
    }
    if (s->state == IS_SEARCH && s->used == 0u) {
        if (!e.has_byte || e.data != 0x55u || e.flags != 0u) {
            s->diag.orphan_events++;
            s->flags = e.flags;
            if (e.flags != 0u) fault(s, IF_UART, e.us);
            drain(s, e.us);
            return;
        }
        s->capture_count = 0u;
        s->evidence_lost = s->flags = s->extra = s->clear_on_tc = 0u;
        s->expected = 0u;
        s->started = e.us;
        s->state = IS_RX;
    }
    save_event(s, e);
    s->last_activity = e.us;
    s->flags |= e.flags;
    if (e.flags != 0u) fault(s, IF_UART, e.us);
    if (s->state == IS_BOUNDARY) {
        if (e.has_byte) {
            s->extra = 1u;
            s->diag.extra_bytes++;
            fault(s, IF_LENGTH, e.us);
        }
        return;
    }
    if (!e.has_byte) return; /* A no-byte error does not manufacture a 00 byte. */
    if (s->used >= sizeof s->frame) {
        fault(s, IF_LENGTH, e.us); drain(s, e.us); return;
    }
    s->frame[s->used++] = e.data;
    if (s->used == 2u) {
        if (e.data == 0xeeu) s->expected = 12u;
        else if (e.data != 0xaau && e.data != 0xccu) {
            fault(s, IF_HEADER, e.us); drain(s, e.us); return;
        }
    }
    if (s->used == 3u && e.data != 2u) {
        fault(s, IF_HEADER, e.us); drain(s, e.us); return;
    }
    if (s->used == 20u && s->frame[1] == 0xccu) {
        uint16_t total = img_read_be16(s->frame + 18u);
        if (total == 0u || total > IMG_MAX_ITEMS) {
            fault(s, IF_LENGTH, e.us); drain(s, e.us); return;
        }
        s->expected = (uint16_t)(56u + 2u * total);
    }
    if (s->used == 20u && s->frame[1] == 0xaau) {
        uint16_t len = img_read_be16(s->frame + 18u);
        if (len == 0u || len > IMG_MAX_PAYLOAD) {
            fault(s, IF_LENGTH, e.us); drain(s, e.us); return;
        }
        s->expected = (uint16_t)(22u + len);
    }
    if (s->expected != 0u && s->used == s->expected) s->state = IS_BOUNDARY;
}
void img_stream_poll(img_stream_t *s, uint32_t now, uint8_t quiet)
{
    if (!quiet && s->state != IS_TX) {
        /* Pin activity affects idle qualification, not last received-byte timeout.
         * A stuck-low RX must still hit the local watchdog. */
        /* SEARCH already earned a complete qualified idle window. The start
         * bit precedes RXNE: revoking SEARCH on that low level would discard
         * the very frame we are waiting for. Only a received byte/error may
         * decide admission there. Boot/drain and boundary guards stay strict. */
        if (s->state == IS_DRAIN) {
            s->state = IS_DRAIN;
            s->last_activity = now;
        } else if (s->state == IS_BOUNDARY) {
            if (!s->extra) {
                s->extra = 1u;
                fault(s, IF_LENGTH, now);
            }
            s->last_activity = now;
        }
    }
    advance(s, now, (uint8_t)!quiet);
}
void img_stream_overflow(img_stream_t *s, uint32_t now)
{
    s->evidence_lost = 1u;
    fault(s, IF_OVERFLOW, now);
    if (s->state != IS_TX) drain(s, now);
    else s->last_activity = now;
}
void img_stream_rx_activity(img_stream_t *s, uint32_t observed_us)
{
    if (s->state == IS_BOUNDARY) {
        if (!s->extra) fault(s, IF_LENGTH, observed_us);
        s->extra = 1u;
        s->last_activity = observed_us;
    } else if (s->state == IS_DRAIN) {
        s->last_activity = observed_us;
    }
    /* SEARCH waits for the actual byte; RX timing remains byte/error based.
     * Do not let ordinary data-bit edges block reception of the first SOF. */
}
void img_stream_tx_inhibited(img_stream_t *s, uint32_t now)
{
    if (s->state != IS_TX) return;
    fault(s, IF_BUSY, now);
    s->clear_on_tc = 0u;
    drain(s, now);
}
void img_stream_tx_complete(img_stream_t *s, uint32_t now)
{
    if (s->state != IS_TX) return;
    s->diag.tx_done++;
    if (s->tx_len >= 20u && s->tx[1] == 0xbbu && s->tx[15] == IMG_STATUS_OK)
        s->diag.frames_ok++;
    if (s->clear_on_tc) s->config.valid = 0u;
    s->clear_on_tc = 0u;
    drain(s, now);
}
void img_stream_tx_failed(img_stream_t *s, uint32_t now)
{
    fault(s, IF_TX_TIMEOUT, now);
    s->clear_on_tc = 0u;
    drain(s, now);
}
uint8_t img_ring_push(img_ring_t *r, img_event_t e)
{
    uint16_t next = (uint16_t)((r->head + 1u) & (IMG_RING_CAP - 1u));
    uint16_t used;
    if (next == r->tail) { r->overflow++; return 0u; }
    r->events[r->head] = e;
    EVENT_BARRIER();
    r->head = next;
    used = (uint16_t)((next - r->tail) & (IMG_RING_CAP - 1u));
    if (used > r->high_water) r->high_water = used;
    return 1u;
}
uint8_t img_ring_pop(img_ring_t *r, img_event_t *e)
{
    if (r->tail == r->head) return 0u;
    EVENT_BARRIER();
    *e = r->events[r->tail];
    EVENT_BARRIER();
    r->tail = (uint16_t)((r->tail + 1u) & (IMG_RING_CAP - 1u));
    return 1u;
}
