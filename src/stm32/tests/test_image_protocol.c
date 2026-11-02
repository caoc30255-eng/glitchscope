#include "image_protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;

#define CHECK(condition) do { \
    ++checks; \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

static size_t load(const char *folder, const char *name,
                   uint8_t *buffer, size_t capacity)
{
    char path[1024];
    FILE *file;
    size_t n;
    if (snprintf(path, sizeof path, "%s/%s", folder, name) >= (int)sizeof path)
        return 0u;
    file = fopen(path, "rb");
    if (file == NULL) return 0u;
    n = fread(buffer, 1u, capacity, file);
    if (fgetc(file) != EOF) n = 0u; /* Reject an oversized input. */
    fclose(file);
    return n;
}

static int case_run(const char *folder)
{
    uint8_t config_frame[IMG_MAX_CONFIG_FRAME];
    uint8_t config_ack[12];
    uint8_t request[IMG_MAX_REQUEST_FRAME];
    uint8_t expected_report[IMG_MAX_REPORT_FRAME];
    uint8_t cleanup[12];
    uint8_t cleanup_ack[12];
    uint8_t output[IMG_MAX_REPORT_FRAME];
    uint8_t bad[IMG_MAX_REQUEST_FRAME];
    img_config_t config;
    img_config_t unchanged;
    img_item_t item;
    img_item_t bad_item;
    size_t nc, na, nr, ne, nl, nca;
    size_t n;

    memset(&config, 0, sizeof config);
    nc = load(folder, "config.bin", config_frame, sizeof config_frame);
    na = load(folder, "config_ack.bin", config_ack, sizeof config_ack);
    nr = load(folder, "request.bin", request, sizeof request);
    ne = load(folder, "expected_report.bin", expected_report, sizeof expected_report);
    nl = load(folder, "cleanup.bin", cleanup, sizeof cleanup);
    nca = load(folder, "cleanup_ack.bin", cleanup_ack, sizeof cleanup_ack);
    CHECK(nc >= 58u && na == 12u && nr >= 23u && ne >= 21u &&
          nl == 12u && nca == 12u);
    CHECK(img_parse_config(config_frame, nc, &config) == IMG_PARSE_OK);
    CHECK(config.valid && config.item_total >= 1u);
    n = img_build_config_ack(&config, output, sizeof output);
    CHECK(n == na && memcmp(output, config_ack, n) == 0);

    unchanged = config;
    config_frame[nc - 1u] ^= 1u;
    CHECK(img_parse_config(config_frame, nc, &config) == IMG_PARSE_FRAME_CRC);
    CHECK(memcmp(&config, &unchanged, sizeof config) == 0);
    config_frame[nc - 1u] ^= 1u;

    CHECK(img_parse_item(request, nr, &config, &item) == IMG_PARSE_OK);
    CHECK(item.safe_candidate && item.frame_crc_ok && item.source_crc_ok);
    CHECK(item.payload_len + 22u == nr);
    n = img_build_report(&item, item.payload, item.payload_len, 0u, 0u,
                         output, sizeof output);
    CHECK(n == ne && memcmp(output, expected_report, n) == 0);
    CHECK(img_build_report(&item, item.payload, item.payload_len, 0u, 0u,
                           output, n - 1u) == 0u);

    memcpy(bad, request, nr);
    bad[nr - 1u] ^= 1u;
    CHECK(img_parse_item(bad, nr, &config, &bad_item) == IMG_PARSE_FRAME_CRC);
    CHECK(bad_item.safe_candidate && !bad_item.frame_crc_ok);
    n = img_build_report(&bad_item, bad_item.payload, bad_item.payload_len,
                         0u, 0u, output, sizeof output);
    CHECK(n == ne && output[15] == IMG_STATUS_REQ_CRC_ERR);
    CHECK(memcmp(output + 18u, item.payload, item.payload_len) == 0);

    memcpy(bad, request, nr);
    bad[20] ^= 1u;
    img_write_be16(bad + nr - 2u, img_crc16(bad + 2u, nr - 4u));
    CHECK(img_parse_item(bad, nr, &config, &bad_item) == IMG_PARSE_SOURCE_CRC);
    CHECK(bad_item.frame_crc_ok && !bad_item.source_crc_ok);
    n = img_build_report(&bad_item, bad_item.payload, bad_item.payload_len,
                         0u, 0u, output, sizeof output);
    CHECK(n == ne && output[15] == IMG_STATUS_REQ_CRC_ERR);
    CHECK(output[18] == bad[20]);
    n = img_build_report(&bad_item, bad_item.payload, bad_item.payload_len,
                         0u, 1u, output, sizeof output);
    CHECK(n == ne && output[15] == IMG_STATUS_LEN_ERR);
    n = img_build_report(&bad_item, bad_item.payload, bad_item.payload_len,
                         0x06u, 1u, output, sizeof output);
    CHECK(n == ne && output[15] == IMG_STATUS_UART_ERR && output[14] == 0x06u);

    memcpy(bad, request, nr);
    bad[3] ^= 1u;
    img_write_be16(bad + nr - 2u, img_crc16(bad + 2u, nr - 4u));
    CHECK(img_parse_item(bad, nr, &config, &bad_item) == IMG_PARSE_CONFIG);
    CHECK(!bad_item.safe_candidate);
    CHECK(img_build_report(&bad_item, request + 20u, item.payload_len,
                           0u, 0u, output, sizeof output) == 0u);

    memcpy(bad, request, nr);
    img_write_be16(bad + 18u, 0u);
    CHECK(img_parse_item(bad, nr, &config, &bad_item) == IMG_PARSE_RANGE);
    img_write_be16(bad + 18u, 513u);
    CHECK(img_parse_item(bad, nr, &config, &bad_item) == IMG_PARSE_RANGE);
    CHECK(img_parse_item(request, nr - 1u, &config, &bad_item) == IMG_PARSE_LENGTH);
    CHECK(img_parse_item(request, nr, &config, &item) == IMG_PARSE_OK);
    n = img_build_report(&item, NULL, 0u, 0u, 1u, output, sizeof output);
    CHECK(n == 20u && output[15] == IMG_STATUS_LEN_ERR &&
          img_read_be16(output + 16u) == 0u);
    CHECK(img_read_be16(output + 18u) == img_crc16(output + 2u, 16u));

    CHECK(img_parse_cleanup(cleanup, nl, &config) == IMG_PARSE_OK);
    n = img_build_cleanup_ack(&config, output, sizeof output);
    CHECK(n == nca && memcmp(output, cleanup_ack, n) == 0);
    cleanup[11] ^= 1u;
    CHECK(img_parse_cleanup(cleanup, nl, &config) == IMG_PARSE_FRAME_CRC);

    printf("CASE_PASS %s payload=%u config_items=%u\n", folder,
           (unsigned)item.payload_len, (unsigned)config.item_total);
    return 0;
}

int main(int argc, char **argv)
{
    int i;
    const uint8_t standard[] = "123456789";
    CHECK(img_crc16(standard, 9u) == 0x29b1u);
    CHECK(argc > 1);
    for (i = 1; i < argc; ++i)
        if (case_run(argv[i]) != 0) return 1;
    printf("C_PROTOCOL_OFFLINE_PASS checks=%u cases=%d\n", checks, argc - 1);
    return 0;
}
