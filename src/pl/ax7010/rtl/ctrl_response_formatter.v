`timescale 1ns / 1ps

module ctrl_response_formatter #(
    parameter integer MAX_PAYLOAD = 32
)(
    // ====================================================================
    // Response kind
    //
    // 0 = RSP_ACK
    // 1 = RSP_NACK
    // 2 = RSP_RESULT
    //
    // Other values are invalid.
    // ====================================================================

    input  wire [1:0]                   response_kind,


    // ====================================================================
    // ACK / NACK common information
    // ====================================================================

    input  wire [7:0]                   original_cmd_type,

    input  wire [15:0]                  trial_id,


    // ====================================================================
    // ACK information
    // ====================================================================

    input  wire [7:0]                   status_code,


    // ====================================================================
    // NACK information
    // ====================================================================

    input  wire [7:0]                   error_layer,

    input  wire [7:0]                   error_code,


    // ====================================================================
    // RESULT information
    // ====================================================================

    input  wire [2:0]                   a_result,
    input  wire [7:0]                   a_byte,
    input  wire                         a_fe,
    input  wire [1:0]                   a_event_count,

    input  wire [2:0]                   b_result,
    input  wire [7:0]                   b_byte,
    input  wire                         b_fe,
    input  wire [1:0]                   b_event_count,

    input  wire                         fault_seen,


    // ====================================================================
    // Formatted packet request
    //
    // Connect later to ctrl_response_packet_encoder:
    //
    // packet_type
    // packet_len
    // packet_payload
    // ====================================================================

    output reg                          format_valid,

    output reg [7:0]                    packet_type,

    output reg [7:0]                    packet_len,

    output reg [MAX_PAYLOAD*8-1:0]      packet_payload
);


    // ====================================================================
    // Response kinds
    // ====================================================================

    localparam [1:0]
        KIND_ACK    = 2'd0,
        KIND_NACK   = 2'd1,
        KIND_RESULT = 2'd2;


    // ====================================================================
    // Protocol response TYPE
    // ====================================================================

    localparam [7:0]
        RSP_ACK    = 8'h80,
        RSP_NACK   = 8'h81,
        RSP_RESULT = 8'h82;


    // ====================================================================
    // Payload lengths
    // ====================================================================

    localparam [7:0]
        ACK_LEN    = 8'd4,
        NACK_LEN   = 8'd5,
        RESULT_LEN = 8'd11;


    // ====================================================================
    // Formatter
    // ====================================================================

    always @(*) begin

        // ----------------------------------------------------------------
        // Default:
        //
        // invalid response kind generates no valid packet.
        //
        // Entire payload is explicitly cleared so that unused bytes
        // cannot leak stale information.
        // ----------------------------------------------------------------

        format_valid =
            1'b0;

        packet_type =
            8'h00;

        packet_len =
            8'd0;

        packet_payload =
            {MAX_PAYLOAD*8{1'b0}};


        case (response_kind)


            // ============================================================
            // RSP_ACK
            //
            // Byte0 = original command type
            // Byte1 = trial ID low
            // Byte2 = trial ID high
            // Byte3 = command-specific status
            // ============================================================

            KIND_ACK: begin

                format_valid =
                    1'b1;

                packet_type =
                    RSP_ACK;

                packet_len =
                    ACK_LEN;


                packet_payload[7:0] =
                    original_cmd_type;

                packet_payload[15:8] =
                    trial_id[7:0];

                packet_payload[23:16] =
                    trial_id[15:8];

                packet_payload[31:24] =
                    status_code;

            end


            // ============================================================
            // RSP_NACK
            //
            // Byte0 = original command type
            // Byte1 = trial ID low
            // Byte2 = trial ID high
            // Byte3 = error layer
            // Byte4 = error code
            // ============================================================

            KIND_NACK: begin

                format_valid =
                    1'b1;

                packet_type =
                    RSP_NACK;

                packet_len =
                    NACK_LEN;


                packet_payload[7:0] =
                    original_cmd_type;

                packet_payload[15:8] =
                    trial_id[7:0];

                packet_payload[23:16] =
                    trial_id[15:8];

                packet_payload[31:24] =
                    error_layer;

                packet_payload[39:32] =
                    error_code;

            end


            // ============================================================
            // RSP_RESULT
            //
            // Byte0  = trial ID low
            // Byte1  = trial ID high
            //
            // Byte2  = A result
            // Byte3  = A byte
            // Byte4  = A FE
            // Byte5  = A event count
            //
            // Byte6  = B result
            // Byte7  = B byte
            // Byte8  = B FE
            // Byte9  = B event count
            //
            // Byte10 = fault seen
            //
            // Boolean / narrow fields are zero-extended so that protocol
            // bytes have canonical values.
            // ============================================================

            KIND_RESULT: begin

                format_valid =
                    1'b1;

                packet_type =
                    RSP_RESULT;

                packet_len =
                    RESULT_LEN;


                // Trial identity

                packet_payload[7:0] =
                    trial_id[7:0];

                packet_payload[15:8] =
                    trial_id[15:8];


                // Receiver A

                packet_payload[23:16] =
                    {5'b00000, a_result};

                packet_payload[31:24] =
                    a_byte;

                packet_payload[39:32] =
                    {7'b0000000, a_fe};

                packet_payload[47:40] =
                    {6'b000000, a_event_count};


                // Receiver B

                packet_payload[55:48] =
                    {5'b00000, b_result};

                packet_payload[63:56] =
                    b_byte;

                packet_payload[71:64] =
                    {7'b0000000, b_fe};

                packet_payload[79:72] =
                    {6'b000000, b_event_count};


                // FaultStim observation

                packet_payload[87:80] =
                    {7'b0000000, fault_seen};

            end


            // ============================================================
            // Invalid response kind
            // ============================================================

            default: begin

                format_valid =
                    1'b0;

                packet_type =
                    8'h00;

                packet_len =
                    8'd0;

            end

        endcase

    end

endmodule