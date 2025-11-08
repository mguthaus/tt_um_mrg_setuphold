// Behavioral wrapper for Sky130 primitives with timing modeling
// This is a simplified model for testing the delay chain concept

`timescale 1ns/1ps

// D Flip-Flop with enforced setup/hold timing - outputs 0 on violations
module sky130_fd_sc_hd__dfxtp_1 (
    input D,
    input CLK,
    output Q,
    input  VPWR,
    input  VGND,
    input  VPB ,
    input  VNB 
);

    parameter SETUP_TIME = 5.0;  // 5ns setup time (exaggerated for testing)
    parameter HOLD_TIME = 2.5;   // 2.5ns hold time (exaggerated for testing)

    reg Q_reg;
    real last_D_change;
    real last_CLK_posedge;

    initial begin
        Q_reg = 1'b0;
        last_D_change = -1000.0;
        last_CLK_posedge = -1000.0;
    end

    // Track when D changes
    always @(D) begin
        last_D_change = $realtime;
    end

    // D flip-flop behavior with timing checks
    always @(posedge CLK) begin
        real time_since_d_change;
        real time_to_next_d_check;

        time_since_d_change = $realtime - last_D_change;
        last_CLK_posedge = $realtime;

        // Check for setup violation (D changed too recently before CLK edge)
        // Check for hold violation (will be detected on next D change)
        if (time_since_d_change < SETUP_TIME && time_since_d_change >= 0) begin
            // Setup violation: D changed too close to clock edge
            // Hold previous value (fail to capture new value)
            Q_reg <= #0.001 Q_reg;
        end else begin
            // Normal operation
            Q_reg <= #0.001 D;
        end
    end

    // Check for hold violations (D changes too soon after CLK edge)
    always @(D) begin
        real time_since_clk;
        time_since_clk = $realtime - last_CLK_posedge;

        if (time_since_clk < HOLD_TIME && time_since_clk > 0) begin
            // Hold violation: D changed too soon after clock edge
            // Output the new (incorrect) value that caused the violation
            Q_reg <= #0.001 D;
        end
    end

    assign Q = Q_reg;

endmodule

// Inverter with propagation delay
module sky130_fd_sc_hd__inv_1 (
    input A,
    output Y,
    input  VPWR,
    input  VGND,
    input  VPB ,
    input  VNB 
);

    parameter DELAY = 0.05;  // 50ps propagation delay

    // Behavioral inverter with delay
    // Non-blocking assignment with inertial delay
    reg Y_reg;

    always @(A) begin
        Y_reg <= #DELAY ~A;
    end

    assign Y = Y_reg;

endmodule
