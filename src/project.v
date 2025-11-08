/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_mrg_setuphold(
    input  wire [7:0] ui_in,    // ui_in[7]=mode (0=test, 1=ring osc)
    output wire [7:0] uo_out,   // Dedicated Outputs - serial data (continuous) and control
    input  wire [7:0] uio_in,   // IOs: Input path - unused
    output wire [7:0] uio_out,  // IOs: Output path - debug/monitoring
    output wire [7:0] uio_oe,   // IOs: Enable path
    input  wire       ena,      // Always enabled
    input  wire       clk,      // Test clock
    input  wire       rst_n     // Reset_n - low to reset
);

    // Mode control
    wire ring_osc_mode;
    assign ring_osc_mode = ui_in[7];

    // --- 1. Clock Inverter Delay Chain (129 stages, odd for ring osc) ---
    (* dont_touch = "true" *) wire [128:0] delayed_clk;

    reg clk_chain_input;
    always @(*) begin
        clk_chain_input = ring_osc_mode ? delayed_clk[128] : clk;
    end

    // First inverter (stage 0)
    (* dont_touch = "true" *)
    sky130_fd_sc_hd__inv_1 clk_inv_0 (
        .A(clk_chain_input),
        .Y(delayed_clk[0])
`ifdef GL_TEST
    ,.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR)
`endif
    );

    // Remaining 128 inverters (stages 1-128)
    genvar i;
    generate
        for (i = 1; i < 129; i = i + 1) begin : inv_chain
            (* dont_touch = "true" *) wire inv_in;
            assign inv_in = delayed_clk[i-1];

            (* dont_touch = "true" *)
            sky130_fd_sc_hd__inv_1 clk_inv (
                .A(inv_in),
                .Y(delayed_clk[i])
`ifdef GL_TEST
    ,.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR)
`endif
            );
        end
    endgenerate

    // --- 2. Data Delay Chain (257 stages for odd-number ring osc) ---
    (* dont_touch = "true" *) wire [256:0] delayed_data;

    reg data_chain_input;

    // Test data generator - forward declaration (assigned later after test_state)
    wire test_data_source;

    always @(*) begin
        data_chain_input = ring_osc_mode ? delayed_data[256] : test_data_source;
    end

    // First inverter (stage 0)
    (* dont_touch = "true" *)
    sky130_fd_sc_hd__inv_1 data_inv_0 (
        .A(data_chain_input),
        .Y(delayed_data[0])
`ifdef GL_TEST
    ,.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR)
`endif
    );

    // Remaining 256 inverters (stages 1-256)
    genvar j;
    generate
        for (j = 1; j < 257; j = j + 1) begin : data_inv_chain
            (* dont_touch = "true" *) wire data_inv_in;
            assign data_inv_in = delayed_data[j-1];

            (* dont_touch = "true" *)
            sky130_fd_sc_hd__inv_1 data_inv (
                .A(data_inv_in),
                .Y(delayed_data[j])
`ifdef GL_TEST
    ,.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR)
`endif
            );
        end
    endgenerate

    // --- 3. PLL-Style Tracking Indices ---
    // Clock fixed at 128 inverter delays, data delay varies with index
    // Data delay = (index + 1) * inverter_delay
    // Indices start at 1, adjust by ±2 to maintain odd polarity
    reg [7:0] setup_index;
    reg [7:0] hold_index;

    // --- 4. Setup Time Test DFF Signal Selection ---
    // Ring osc mode: delayed_clk[127], test_data_source
    // Test mode: CLK uses fixed delay (delayed_clk[127]), D varies with setup_index
    // This measures setup time by varying data delay relative to fixed clock
    wire setup_selected_clk;
    wire setup_selected_data;
    assign setup_selected_clk = delayed_clk[127];  // Same for both modes
    assign setup_selected_data = ring_osc_mode ? test_data_source : delayed_data[setup_index];

    wire setup_test_output;
    (* dont_touch = "true" *)
    sky130_fd_sc_hd__dfxtp_1 setup_test_dff (
        .D(setup_selected_data),
        .CLK(setup_selected_clk),
        .Q(setup_test_output)
`ifdef GL_TEST
    ,.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR)
`endif
    );

    // --- 5. Hold Time Test DFF Signal Selection ---
    // Ring osc mode: delayed_data[256], delayed_clk[127]
    // Test mode: CLK uses fixed delay (delayed_clk[127]), D varies with hold_index
    // This measures hold time by varying data delay relative to fixed clock
    wire hold_selected_clk;
    wire hold_selected_data;
    assign hold_selected_clk = delayed_clk[127];  // Same for both modes
    assign hold_selected_data = ring_osc_mode ? delayed_data[256] : delayed_data[hold_index];

    wire hold_test_output;
    (* dont_touch = "true" *)
    sky130_fd_sc_hd__dfxtp_1 hold_test_dff (
        .D(hold_selected_data),
        .CLK(hold_selected_clk),
        .Q(hold_test_output)
`ifdef GL_TEST
    ,.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR)
`endif
    );

    // --- 6. Capture and Compare ---
    // Use test_data_source directly (no need for expected_output register)

    // Simple 3-state machine for testing: state 0 (D=0), state 1 (D=1), state 3 (update)
    reg [1:0] test_state;
    reg setup_passed_d0;
    reg setup_passed_d1;
    reg hold_passed_d0;
    reg hold_passed_d1;

    // Test data source is lowest bit of test_state
    // State 0: test_data_source = 0
    // State 1: test_data_source = 1
    // State 3: test_data_source = 1
    assign test_data_source = test_state[0];

    // State machine and test result capture
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            test_state <= 2'd0;
            setup_passed_d0 <= 1'b0;
            setup_passed_d1 <= 1'b0;
            hold_passed_d0 <= 1'b0;
            hold_passed_d1 <= 1'b0;
        end else if (ena && !ring_osc_mode) begin
            case (test_state)
                2'd0: begin
                    // State 0: Test with D=0
                    setup_passed_d0 <= (setup_test_output == test_data_source);
                    hold_passed_d0 <= (hold_test_output == test_data_source);
                    test_state <= 2'd1;
                end
                2'd1: begin
                    // State 1: Test with D=1
                    setup_passed_d1 <= (setup_test_output == test_data_source);
                    hold_passed_d1 <= (hold_test_output == test_data_source);
                    test_state <= 2'd3;
                end
                2'd3: begin
                    // State 3: Update indices (done in separate always blocks)
                    test_state <= 2'd0;
                end
                default: test_state <= 2'd0;
            endcase
        end
    end

    // Update index signal asserted during state 3
    wire update_index;
    assign update_index = (test_state == 2'd3) && ena && !ring_osc_mode;

    // Overall pass/fail for each DFF
    wire setup_passed;
    wire hold_passed;
    assign setup_passed = setup_passed_d0 && setup_passed_d1;
    assign hold_passed = hold_passed_d0 && hold_passed_d1;

    // --- 7. PLL-Style Index Tracking ---
    // IMPORTANT: For proper operation, max delay must be less than clock period
    //   Max delay = 256 inverters × ~50ps = ~12.8ns
    //   Recommended min clock period: 20ns (50MHz max frequency)
    //   If max delay > clock period, delayed clock arrives after next edge → incorrect operation

    // Setup index: tracks data delay for setup time measurement
    // Clock fixed at delayed_clk[127] (128 inverter delays)
    // Data delay = setup_index+1 inverter delays
    // Start at 1 (minimal delay), increment to find where setup fails
    // NOTE: Increment/decrement by 2 to preserve signal polarity through inverter chain
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            setup_index <= 8'd1;  // Start with minimal delay (2 inversions, plenty of setup time)
        end else if (update_index) begin
            // Update only during state 2 based on test results
            // Step by 2 to preserve polarity
            if (!setup_passed && setup_index > 8'd1)
                setup_index <= setup_index - 8'd2;  // Failed (setup violation), make data earlier
            else if (setup_passed && setup_index < 8'd254)
                setup_index <= setup_index + 8'd2;  // Passed, make data later to find boundary
        end
    end

    // Hold index: tracks data delay for hold time measurement
    // Clock fixed at delayed_clk[127] (128 inverter delays)
    // Data delay = hold_index+1 inverter delays
    // Start at maximum delay (255) so it initially fails, then decrease to find boundary
    // NOTE: Increment/decrement by 2 to preserve signal polarity through inverter chain
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hold_index <= 8'd255;  // Start at maximum delay (256 inversions, will fail hold)
        end else if (update_index) begin
            // Update only during state 2 based on test results
            // Step by 2 to preserve polarity
            if (!hold_passed && hold_index > 8'd1)
                hold_index <= hold_index - 8'd2;  // Failed (hold violation), make data earlier
            else if (hold_passed && hold_index < 8'd254)
                hold_index <= hold_index + 8'd2;  // Passed, make data later to find boundary
        end
    end

    // --- 8. Ring Oscillator Frequency Counters ---
    // Counters are clocked by the ring oscillators themselves to avoid missing edges
    // Asynchronously reset by rst_n, synchronously reset when shift_valid is true
    reg [15:0] clk_ring_count;
    reg [15:0] data_ring_count;

    // Clock ring oscillator counter - clocked by the clock ring oscillator
    // Asynchronous reset with rst_n, synchronous reset with shift_valid
    // Only count when in ring_osc_mode
    wire count_clk = delayed_clk[128];
    always @(posedge count_clk or negedge rst_n) begin
        if (!rst_n) begin
            clk_ring_count <= 16'h0000;  // Async reset
        end else if (shift_valid) begin
            clk_ring_count <= 16'h0000;  // Sync reset when capturing value
        end else if (ring_osc_mode) begin
            clk_ring_count <= clk_ring_count + 16'd1;  // Only count in ring osc mode
        end
    end

    // Data ring oscillator counter - clocked by the data ring oscillator
    // Asynchronous reset with rst_n, synchronous reset with shift_valid
    // Only count when in ring_osc_mode
    wire count_data = delayed_data[256];
    always @(posedge count_data or negedge rst_n) begin
        if (!rst_n) begin
            data_ring_count <= 16'h0000;  // Async reset
        end else if (shift_valid) begin
            data_ring_count <= 16'h0000;  // Sync reset when capturing value
        end else if (ring_osc_mode) begin
            data_ring_count <= data_ring_count + 16'd1;  // Only count in ring osc mode
        end
    end

    // --- 9. Serial Output Shift Register ---
    reg [31:0] shift_reg;      // 32 bits for both modes
    reg [5:0] shift_counter;   // Count bits shifted (0-31)
    reg shift_valid;           // High during first bit

    // Shift register control - continuously shifts every clock cycle
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shift_reg <= 32'h0;
            shift_counter <= 6'd0;
            shift_valid <= 1'b0;
        end else if (ena) begin
            // 32 bits in both modes
            if (shift_counter == 6'd0) begin
                // Load new data based on mode
                shift_reg <= ring_osc_mode ?
                             {clk_ring_count, data_ring_count} :  // Ring osc: counts
                             {8'h0, setup_index, 8'h0, hold_index};  // Test: padded indices
                shift_valid <= 1'b1;  // First bit
                shift_counter <= 6'd1;
            end else if (shift_counter < 6'd32) begin
                // Shift out data
                shift_reg <= {shift_reg[30:0], 1'b0};
                shift_valid <= 1'b0;
                shift_counter <= shift_counter + 6'd1;
            end else begin
                // Done, reset to reload on next cycle
                shift_counter <= 6'd0;
                shift_valid <= 1'b0;
            end
        end
    end

    // --- 10. Output Assignments ---
    assign uo_out[0] = shift_reg[31];           // Serial data output (MSB first)
    assign uo_out[1] = shift_valid;             // Valid flag (high on first bit)
    assign uo_out[2] = !setup_passed;           // Debug: setup failed
    assign uo_out[3] = !hold_passed;            // Debug: hold failed
    assign uo_out[4] = setup_test_output;       // Debug: setup DFF output
    assign uo_out[5] = hold_test_output;        // Debug: hold DFF output
    assign uo_out[6] = ring_osc_mode ? delayed_clk[128] : 1'b0;   // Debug: ring osc
    assign uo_out[7] = ring_osc_mode ? delayed_data[256] : 1'b0;  // Debug: ring osc

    // Monitoring outputs: current indices or counter lower bits
    assign uio_out = ring_osc_mode ?
                     {clk_ring_count[7:0]} :     // Lower 8 bits of clk counter
                     {setup_index[7:0]};         // Current setup index

    assign uio_oe = 8'hFF;

endmodule
