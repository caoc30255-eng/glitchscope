#include "image_protocol.h"

#include <string.h>

#define IMG_VERSION 2u

uint16_t img_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xffffu;
    size_t i;
    unsigned bit;
    if (data == NULL && len != 0u) return 0u;
    for (i = 0u; i < len; ++i) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (bit = 0u; bit < 8u; ++bit) {
            crc = (uint16_t)((crc & 0x8000u) != 0u
                ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1));
        }
    }
    return crc;
}

uint16_t img_read_be16(const uint8_t *data)
{
    return (uint16_t)(((uint16_t)data[0] << 8) | data[1]);
}

uint32_t img_read_be32(const uint8_t *data)
{
    return ((uint32_t)data[0] << 24) | ((uint32_t)data[1] << 16)
         | ((uint32_t)data[2] << 8) | data[3];
}

void img_write_be16(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)(value >> 8);
    data[1] = (uint8_t)value;
}

void img_write_be32(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)(value >> 24);
    data[1] = (uint8_t)(value >> 16);
    data[2] = (uint8_t)(value >> 8);
    data[3] = (uint8_t)value;
}

img_parse_result_t img_parse_config(const uint8_t *frame, size_t len,
                                     img_config_t *config_out)
{
    img_config_t candidate;
    uint16_t total;
    uint16_t chunk;
    uint32_t bytes;
    uint32_t product;
    uint32_t expected_items;
    size_t expected_len;
    uint16_t i;

    if (frame == NULL || config_out == NULL) return IMG_PARSE_ARGUMENT;
    if (len < 58u) return IMG_PARSE_LENGTH;
    if (frame[0] != 0x55u || frame[1] != 0xccu) return IMG_PARSE_SOF;
    if (frame[2] != IMG_VERSION) return IMG_PARSE_VERSION;
    if (frame[8] != 1u || frame[9] != 0u) return IMG_PARSE_RANGE;
    total = img_read_be16(frame + 18u);
    chunk = img_read_be16(frame + 20u);
    if (total == 0u || total > IMG_MAX_ITEMS || chunk == 0u ||
        chunk > IMG_MAX_PAYLOAD) return IMG_PARSE_RANGE;
    expected_len = 56u + (size_t)2u * total;
    if (len != expected_len) return IMG_PARSE_LENGTH;
    bytes = img_read_be32(frame + 14u);
    product = (uint32_t)img_read_be16(frame + 10u) *
              (uint32_t)img_read_be16(frame + 12u);
    expected_items = (bytes + (uint32_t)chunk - 1u) / chunk;
    if (bytes == 0u || bytes != product || expected_items != total)
        return IMG_PARSE_RANGE;
    if (img_crc16(frame + 2u, len - 4u) != img_read_be16(frame + len - 2u))
        return IMG_PARSE_FRAME_CRC;

    memset(&candidate, 0, sizeof candidate);
    candidate.valid = 1u;
    candidate.run_id = img_read_be32(frame + 3u);
    candidate.image_id = frame[7];
    candidate.width = img_read_be16(frame + 10u);
    candidate.height = img_read_be16(frame + 12u);
    candidate.total_bytes = bytes;
    candidate.item_total = total;
    candidate.chunk_size = chunk;
    memcpy(candidate.original_sha256, frame + 22u, 32u);
    for (i = 0u; i < total; ++i)
        candidate.item_crc[i] = img_read_be16(frame + 54u + (size_t)2u * i);
    *config_out = candidate;
    return IMG_PARSE_OK;
}

img_parse_result_t img_parse_item_header(const uint8_t *frame, size_t len,
                                   const img_config_t *config,
                                   img_item_t *item_out)
{
    img_item_t candidate;
    uint16_t index;
    uint16_t total;
    uint16_t payload_len;
    uint32_t remaining;
    uint16_t expected_payload_len;

    if (frame == NULL || config == NULL || item_out == NULL)
        return IMG_PARSE_ARGUMENT;
    memset(item_out, 0, sizeof *item_out);
    if (len < 20u) return IMG_PARSE_LENGTH;
    if (frame[0] != 0x55u || frame[1] != 0xaau) return IMG_PARSE_SOF;
    if (frame[2] != IMG_VERSION) return IMG_PARSE_VERSION;
    index = img_read_be16(frame + 10u);
    total = img_read_be16(frame + 12u);
    payload_len = img_read_be16(frame + 18u);
    if (total == 0u || total > IMG_MAX_ITEMS || index >= total ||
        frame[14] > 3u || frame[15] > 1u || payload_len == 0u ||
        payload_len > IMG_MAX_PAYLOAD) return IMG_PARSE_RANGE;
    if (!config->valid || img_read_be32(frame + 3u) != config->run_id ||
        frame[7] != config->image_id || total != config->item_total)
        return IMG_PARSE_CONFIG;
    remaining = config->total_bytes - (uint32_t)index * config->chunk_size;
    expected_payload_len = (uint16_t)(remaining < config->chunk_size
                                     ? remaining : config->chunk_size);
    if (payload_len != expected_payload_len ||
        img_read_be16(frame + 16u) != config->item_crc[index])
        return IMG_PARSE_CONFIG;

    memset(&candidate, 0, sizeof candidate);
    candidate.safe_candidate = 1u;
    candidate.run_id = config->run_id;
    candidate.image_id = config->image_id;
    candidate.trial_id = img_read_be16(frame + 8u);
    candidate.item_index = index;
    candidate.item_total = total;
    candidate.attempt_id = frame[14];
    candidate.route_mode = frame[15];
    candidate.source_crc = img_read_be16(frame + 16u);
    candidate.payload_len = payload_len;
    candidate.payload = frame + 20u;
    *item_out = candidate;
    return IMG_PARSE_OK;
}

img_parse_result_t img_parse_item(const uint8_t *frame, size_t len,
                                   const img_config_t *config,
                                   img_item_t *item_out)
{
    img_item_t candidate;
    img_parse_result_t result = img_parse_item_header(frame, len, config, &candidate);
    if (item_out == NULL) return IMG_PARSE_ARGUMENT;
    memset(item_out, 0, sizeof *item_out);
    if (result != IMG_PARSE_OK) return result;
    if (len != 22u + (size_t)candidate.payload_len) return IMG_PARSE_LENGTH;
    candidate.frame_crc_ok = (uint8_t)(img_crc16(frame + 2u, len - 4u)
                                      == img_read_be16(frame + len - 2u));
    candidate.source_crc_ok = (uint8_t)(img_crc16(candidate.payload, candidate.payload_len)
                                       == candidate.source_crc);
    *item_out = candidate;
    if (!candidate.frame_crc_ok) return IMG_PARSE_FRAME_CRC;
    if (!candidate.source_crc_ok) return IMG_PARSE_SOURCE_CRC;
    return IMG_PARSE_OK;
}

img_parse_result_t img_parse_cleanup(const uint8_t *frame, size_t len,
                                      const img_config_t *config)
{
    if (frame == NULL || config == NULL) return IMG_PARSE_ARGUMENT;
    if (len != 12u) return IMG_PARSE_LENGTH;
    if (frame[0] != 0x55u || frame[1] != 0xeeu) return IMG_PARSE_SOF;
    if (frame[2] != IMG_VERSION) return IMG_PARSE_VERSION;
    if (!config->valid || img_read_be32(frame + 3u) != config->run_id ||
        frame[7] != config->image_id || img_read_be16(frame + 8u) != 1u)
        return IMG_PARSE_CONFIG;
    if (img_crc16(frame + 2u, 8u) != img_read_be16(frame + 10u))
        return IMG_PARSE_FRAME_CRC;
    return IMG_PARSE_OK;
}

static size_t build_ack(uint8_t sof_low, const img_config_t *config,
                        uint8_t *out, size_t capacity)
{
    uint16_t crc;
    if (config == NULL || !config->valid || out == NULL || capacity < 12u)
        return 0u;
    out[0] = 0x55u;
    out[1] = sof_low;
    out[2] = IMG_VERSION;
    img_write_be32(out + 3u, config->run_id);
    out[7] = config->image_id;
    img_write_be16(out + 8u, 0u);
    crc = img_crc16(out + 2u, 8u);
    img_write_be16(out + 10u, crc);
    return 12u;
}

size_t img_build_config_ack(const img_config_t *config, uint8_t *out,
                            size_t capacity)
{
    return build_ack(0xcdu, config, out, capacity);
}

size_t img_build_cleanup_ack(const img_config_t *config, uint8_t *out,
                             size_t capacity)
{
    return build_ack(0xefu, config, out, capacity);
}

size_t img_build_report(const img_item_t *item, const uint8_t *actual_data,
                        size_t actual_len, uint8_t uart_flags,
                        uint8_t length_error, uint8_t *out, size_t capacity)
{
    uint8_t status;
    uint16_t crc;
    size_t total_len;
    if (item == NULL || !item->safe_candidate || out == NULL ||
        (actual_data == NULL && actual_len != 0u) ||
        actual_len > IMG_MAX_PAYLOAD || uart_flags > 0x0fu ||
        capacity < 20u + actual_len)
        return 0u;
    total_len = 20u + actual_len;
    status = (uart_flags != 0u) ? IMG_STATUS_UART_ERR :
             (length_error != 0u || actual_len != item->payload_len) ?
             IMG_STATUS_LEN_ERR :
             (!item->frame_crc_ok || !item->source_crc_ok) ?
             IMG_STATUS_REQ_CRC_ERR : IMG_STATUS_OK;
    out[0] = 0x55u;
    out[1] = 0xbbu;
    out[2] = IMG_VERSION;
    img_write_be32(out + 3u, item->run_id);
    out[7] = item->image_id;
    img_write_be16(out + 8u, item->trial_id);
    img_write_be16(out + 10u, item->item_index);
    out[12] = item->attempt_id;
    out[13] = item->route_mode;
    out[14] = uart_flags;
    out[15] = status;
    img_write_be16(out + 16u, (uint16_t)actual_len);
    if (actual_len != 0u) memcpy(out + 18u, actual_data, actual_len);
    crc = img_crc16(out + 2u, 16u + actual_len);
    img_write_be16(out + 18u + actual_len, crc);
    return total_len;
}
