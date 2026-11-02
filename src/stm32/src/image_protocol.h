#ifndef IMAGE_PROTOCOL_H
#define IMAGE_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

/* v0.6.11 inner image frames only. No H1, GPIO, UART, or timing here. */
#define IMG_MAX_ITEMS 64u
#define IMG_MAX_PAYLOAD 512u
#define IMG_MAX_CONFIG_FRAME (56u + 2u * IMG_MAX_ITEMS)
#define IMG_MAX_REQUEST_FRAME (22u + IMG_MAX_PAYLOAD)
#define IMG_MAX_REPORT_FRAME (20u + IMG_MAX_PAYLOAD)

#define IMG_STATUS_OK 0u
#define IMG_STATUS_REQ_CRC_ERR 1u
#define IMG_STATUS_LEN_ERR 2u
#define IMG_STATUS_UART_ERR 3u

typedef enum {
    IMG_PARSE_OK = 0,
    IMG_PARSE_ARGUMENT,
    IMG_PARSE_LENGTH,
    IMG_PARSE_SOF,
    IMG_PARSE_VERSION,
    IMG_PARSE_RANGE,
    IMG_PARSE_CONFIG,
    IMG_PARSE_FRAME_CRC,
    IMG_PARSE_SOURCE_CRC
} img_parse_result_t;

typedef struct {
    uint8_t valid;
    uint32_t run_id;
    uint8_t image_id;
    uint16_t width;
    uint16_t height;
    uint32_t total_bytes;
    uint16_t item_total;
    uint16_t chunk_size;
    uint8_t original_sha256[32];
    uint16_t item_crc[IMG_MAX_ITEMS];
} img_config_t;

typedef struct {
    uint8_t safe_candidate;
    uint32_t run_id;
    uint8_t image_id;
    uint16_t trial_id;
    uint16_t item_index;
    uint16_t item_total;
    uint8_t attempt_id;
    uint8_t route_mode;
    uint16_t source_crc;
    uint16_t payload_len;
    const uint8_t *payload; /* Points into caller-owned complete request frame. */
    uint8_t frame_crc_ok;
    uint8_t source_crc_ok;
} img_item_t;

uint16_t img_crc16(const uint8_t *data, size_t len);
uint16_t img_read_be16(const uint8_t *data);
uint32_t img_read_be32(const uint8_t *data);
void img_write_be16(uint8_t *data, uint16_t value);
void img_write_be32(uint8_t *data, uint32_t value);

/* On failure config_out is unchanged. Caller controls active-item policy. */
img_parse_result_t img_parse_config(const uint8_t *frame, size_t len,
                                     img_config_t *config_out);
img_parse_result_t img_parse_item(const uint8_t *frame, size_t len,
                                   const img_config_t *config,
                                   img_item_t *item_out);
/* Complete 20 B candidate header only; CRC booleans remain false. */
img_parse_result_t img_parse_item_header(const uint8_t *frame, size_t len,
                                          const img_config_t *config,
                                          img_item_t *item_out);
img_parse_result_t img_parse_cleanup(const uint8_t *frame, size_t len,
                                      const img_config_t *config);

/* Returns encoded length, or zero for invalid arguments/insufficient space. */
size_t img_build_config_ack(const img_config_t *config, uint8_t *out,
                            size_t capacity);
size_t img_build_cleanup_ack(const img_config_t *config, uint8_t *out,
                             size_t capacity);
size_t img_build_report(const img_item_t *item, const uint8_t *actual_data,
                        size_t actual_len, uint8_t uart_flags,
                        uint8_t length_error, uint8_t *out, size_t capacity);

#endif
