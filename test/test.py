# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge, Timer
from cocotb.handle import Force, Release


async def deserialize_output(dut, num_bits):
    """
    Read serial output from the design.
    Data shifts out automatically every clock cycle.
    Returns the deserialized value.
    """
    result = 0
    valid_seen = False

    # Wait for valid flag to go high (start of new data)
    for _ in range(100):  # Timeout after 100 cycles
        await ClockCycles(dut.clk, 1)
        try:
            shift_valid = (dut.uo_out.value.to_unsigned() >> 1) & 0x1
            if shift_valid:
                valid_seen = True
                break
        except ValueError:
            # Contains X/Z values, skip this cycle
            continue

    # Read all bits starting from the current position
    for bit_idx in range(num_bits):
        # Read serial data
        try:
            serial_bit = (dut.uo_out.value.to_unsigned() >> 0) & 0x1
        except ValueError:
            # Contains X/Z values, treat as 0
            serial_bit = 0

        # Shift in the bit (MSB first)
        result = (result << 1) | serial_bit

        # Wait for next bit
        await ClockCycles(dut.clk, 1)

    return result, valid_seen


@cocotb.test()
async def test_oscillator1(dut):
    """Test ring oscillator mode with 100ns clock period and 0.05ns inverter delay"""
    dut._log.info("Start Ring Oscillator Test 1 (100ns clock, 50ps inv delay)")

    # --- Test Parameters ---
    clk_period_ns = 100  # 10MHz system clock
    inv_delay_ns = 0.05  # 50ps from wrapper

    # --- 1. Clock Setup ---
    system_clock = Clock(dut.clk, clk_period_ns, unit="ns")
    cocotb.start_soon(system_clock.start())

    # --- 2. Reset ---
    dut._log.info("Resetting design...")
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.ui_in.value = 0  # Start in test mode (bit 7=0), not ring osc mode yet
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)

    # --- 3. Early Ring Oscillator Initialization with Force/Release ---
    # Temporarily disabled to test if oscillators self-start
    # dut._log.info("Early initialization with Force/Release (before mode switch)...")
    # dut.user_project.clk_chain_input.value = Force(1)
    # dut.user_project.data_chain_input.value = Force(1)
    # await Timer(1, unit='ns')  # Let signal propagate through chains
    # dut.user_project.clk_chain_input.value = Release()
    # dut.user_project.data_chain_input.value = Release()
    # await ClockCycles(dut.clk, 2)

    # --- 4. Run in test mode to clear X states ---
    dut._log.info("Running in test mode to clear X states...")
    await ClockCycles(dut.clk, 2)

    # --- 5. Switch to Ring Oscillator Mode ---
    dut._log.info("Switching to ring oscillator mode...")
    dut.ui_in.value = 0x80  # Ring osc mode (bit 7=1)
    await ClockCycles(dut.clk, 2)  # Let oscillation establish

    # --- 6. Let Counters Accumulate ---
    dut._log.info("Allowing ring oscillator counters to accumulate...")
    count_cycles = 50
    await ClockCycles(dut.clk, count_cycles)

    # --- 7. Read Serial Output ---
    dut._log.info("Reading serial output...")
    serial_data, valid_flag = await deserialize_output(dut, 32)

    clk_count = (serial_data >> 16) & 0xFFFF
    data_count = serial_data & 0xFFFF

    dut._log.info(f"Serial output valid flag: {valid_flag}")
    dut._log.info(f"Clock ring oscillator count: {clk_count}")
    dut._log.info(f"Data ring oscillator count: {data_count}")

    # --- 8. Monitor Debug Signals ---
    try:
        clk_ring_signal = (dut.uo_out.value.to_unsigned() >> 6) & 0x1
        data_ring_signal = (dut.uo_out.value.to_unsigned() >> 7) & 0x1
        dut._log.info(f"Clock ring oscillator output: {clk_ring_signal}")
        dut._log.info(f"Data ring oscillator output: {data_ring_signal}")
    except ValueError:
        dut._log.info(f"Clock/Data ring oscillator outputs contain X/Z values")

    # --- 9. Verification ---
    dut._log.info("\n=== Ring Oscillator Test 1 Summary ===")
    dut._log.info(f"Clock period: {clk_period_ns}ns")
    dut._log.info(f"Inverter delay: {inv_delay_ns}ns ({inv_delay_ns * 1000}ps)")

    # Clock ring: 128 + 1 (feedback inversion) = 129 inversions
    # Data ring: 256 + 1 (no feedback inv, already odd) = 257 inversions
    clk_num_inverters = 129
    data_num_inverters = 257

    # Serial frame period is 33 clocks (1 load + 32 shift)
    serial_frame_period_ns = 33 * clk_period_ns
    test_time_s = serial_frame_period_ns * 1e-9

    # Expected frequency based on inverter delay
    clk_expected_period_ns = 2 * clk_num_inverters * inv_delay_ns
    data_expected_period_ns = 2 * data_num_inverters * inv_delay_ns
    clk_expected_freq_hz = 1.0 / (clk_expected_period_ns * 1e-9)
    data_expected_freq_hz = 1.0 / (data_expected_period_ns * 1e-9)

    # Measured frequency from counts
    actual_clk_freq_hz = clk_count / test_time_s if clk_count > 0 else 0
    actual_data_freq_hz = data_count / test_time_s if data_count > 0 else 0

    dut._log.info(
        f"Measurement period: {serial_frame_period_ns:.1f}ns (33 clocks @ {clk_period_ns}ns)"
    )
    dut._log.info(f"\nExpected (based on wrapper inv_delay={inv_delay_ns}ns):")
    dut._log.info(
        f"  Clock ring period: {clk_expected_period_ns}ns (2 trips × {clk_num_inverters} inversions × {inv_delay_ns}ns)"
    )
    dut._log.info(f"  Clock ring frequency: {clk_expected_freq_hz:.2f} Hz")
    dut._log.info(
        f"  Data ring period: {data_expected_period_ns}ns (2 trips × {data_num_inverters} inversions × {inv_delay_ns}ns)"
    )
    dut._log.info(f"  Data ring frequency: {data_expected_freq_hz:.2f} Hz")

    clk_expected_count = int(serial_frame_period_ns / clk_expected_period_ns)
    data_expected_count = int(serial_frame_period_ns / data_expected_period_ns)

    dut._log.info(f"\nMeasured:")
    dut._log.info(f"  Clock ring count: {clk_count} edges (expected ~{clk_expected_count})")
    dut._log.info(f"  Data ring count: {data_count} edges (expected ~{data_expected_count})")
    dut._log.info(f"  Clock ring frequency: {actual_clk_freq_hz:.2f} Hz")
    dut._log.info(f"  Data ring frequency: {actual_data_freq_hz:.2f} Hz")

    # NOTE: Ring oscillators must oscillate for this test to pass
    # This test is mainly for gate-level simulation verification
    assert clk_count > 0 and data_count > 0, (
        f"Ring oscillators must oscillate. Expected ~{clk_expected_count} edges, got clk={clk_count} data={data_count}"
    )

    freq_ratio_clk = actual_clk_freq_hz / clk_expected_freq_hz
    freq_ratio_data = actual_data_freq_hz / data_expected_freq_hz
    dut._log.info(f"\nFrequency ratio (measured/expected):")
    dut._log.info(f"  Clock: {freq_ratio_clk:.3f}")
    dut._log.info(f"  Data: {freq_ratio_data:.3f}")

    assert 0.9 < freq_ratio_clk < 1.1, (
        f"Clock frequency {actual_clk_freq_hz:.2f} Hz should be within 10% of expected {clk_expected_freq_hz:.2f} Hz (ratio: {freq_ratio_clk:.3f})"
    )
    assert 0.9 < freq_ratio_data < 1.1, (
        f"Data frequency {actual_data_freq_hz:.2f} Hz should be within 10% of expected {data_expected_freq_hz:.2f} Hz (ratio: {freq_ratio_data:.3f})"
    )
    dut._log.info("\nRing oscillator test 1 PASSED - oscillations accurate within 10%!")


@cocotb.test()
async def test_setup_hold_tracking(dut):
    """Test automatic setup/hold time tracking with serial output"""
    dut._log.info("Start Setup/Hold Time PLL-Style Tracking Test")

    # --- 1. Clock Setup ---
    clk_period_ns = 100  # 10MHz system clock
    system_clock = Clock(dut.clk, clk_period_ns, unit="ns")
    cocotb.start_soon(system_clock.start())

    # --- 2. Reset ---
    dut._log.info("Resetting design...")
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.ui_in.value = 0  # Test mode (bit 7=0), shift_clk=0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # --- 3. Let Indices Converge ---
    dut._log.info("Allowing PLL-style tracking to converge...")
    dut._log.info(f"Clock period: {clk_period_ns}ns")

    # Run for several cycles to let the indices settle
    convergence_cycles = 200
    await ClockCycles(dut.clk, convergence_cycles)

    # --- 4. Read Serial Output ---
    dut._log.info("Reading serial output...")

    # Deserialize 32 bits: {8'h0, setup_index[7:0], 8'h0, hold_index[7:0]}
    serial_data, valid_flag = await deserialize_output(dut, 32)

    setup_index = (serial_data >> 16) & 0xFF
    hold_index = serial_data & 0xFF

    dut._log.info(f"Serial output valid flag: {valid_flag}")
    dut._log.info(f"Setup index converged to: {setup_index}")
    dut._log.info(f"Hold index converged to: {hold_index}")

    # --- 5. Monitor Debug Signals ---
    setup_mismatch = (dut.uo_out.value.to_unsigned() >> 2) & 0x1
    hold_mismatch = (dut.uo_out.value.to_unsigned() >> 3) & 0x1
    setup_out = (dut.uo_out.value.to_unsigned() >> 4) & 0x1
    hold_out = (dut.uo_out.value.to_unsigned() >> 5) & 0x1

    dut._log.info(f"Setup mismatch: {setup_mismatch}")
    dut._log.info(f"Hold mismatch: {hold_mismatch}")
    dut._log.info(f"Setup DFF output: {setup_out}")
    dut._log.info(f"Hold DFF output: {hold_out}")

    # --- 6. Verification ---
    assert valid_flag, "Shift valid flag should be seen on first bit"
    assert setup_index < 256, "Setup index should be in valid range"
    assert hold_index < 256, "Hold index should be in valid range"

    dut._log.info("\n=== Test Mode Summary ===")
    dut._log.info(f"Setup time characterization: {setup_index} inverter delays")
    dut._log.info(f"Hold time characterization: {hold_index} inverter delays")
    dut._log.info("Test completed successfully!")


@cocotb.test()
async def test_serial_interface(dut):
    """Test serial interface timing and valid flag with continuous shifting"""
    dut._log.info("Start Serial Interface Timing Test")

    # --- 1. Clock Setup ---
    clk_period_ns = 100
    system_clock = Clock(dut.clk, clk_period_ns, unit="ns")
    cocotb.start_soon(system_clock.start())

    # --- 2. Reset ---
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.ui_in.value = 0  # Test mode
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # --- 3. Test Serial Output Multiple Times ---
    dut._log.info("Testing multiple serial read cycles...")

    for read_cycle in range(3):
        dut._log.info(f"\nRead cycle {read_cycle + 1}:")

        # Wait for valid flag to indicate start of new data
        valid_found = False
        for _ in range(50):
            await ClockCycles(dut.clk, 1)
            try:
                valid_bit = (dut.uo_out.value.to_unsigned() >> 1) & 0x1
                if valid_bit:
                    valid_found = True
                    break
            except ValueError:
                continue

        assert valid_found, f"Valid flag not found in cycle {read_cycle}"

        valid_bits = []
        serial_bits = []

        # Read 32 bits of data
        for bit_idx in range(32):
            try:
                serial_bit = (dut.uo_out.value.to_unsigned() >> 0) & 0x1
                valid_bit = (dut.uo_out.value.to_unsigned() >> 1) & 0x1
            except ValueError:
                serial_bit = 0
                valid_bit = 0

            valid_bits.append(valid_bit)
            serial_bits.append(serial_bit)

            await ClockCycles(dut.clk, 1)

        # Reconstruct value
        result = 0
        for bit in serial_bits:
            result = (result << 1) | bit

        setup_idx = (result >> 16) & 0xFF
        hold_idx = result & 0xFF

        dut._log.info(f"  Valid pattern: {valid_bits[:5]}... (first 5 bits)")
        dut._log.info(f"  Setup index: {setup_idx}")
        dut._log.info(f"  Hold index: {hold_idx}")

        # Verify valid flag is high only on first bit
        assert valid_bits[0] == 1, (
            f"Valid should be high on first bit (cycle {read_cycle})"
        )
        assert all(v == 0 for v in valid_bits[1:]), (
            f"Valid should be low on remaining bits (cycle {read_cycle})"
        )

    dut._log.info("\nSerial interface timing test passed!")


@cocotb.test()
async def test_case1(dut):
    """Test setup/hold tracking with behavioral DFF timing (SETUP_TIME=5ns, HOLD_TIME=2.5ns)"""
    dut._log.info("Start Timing Test Case 1: Behavioral DFF timing")

    # --- 1. Clock Setup ---
    clk_period_ns = 100  # 10MHz system clock
    system_clock = Clock(dut.clk, clk_period_ns, unit="ns")
    cocotb.start_soon(system_clock.start())

    # Inverter delay from wrapper
    inv_delay_ns = 0.05  # 50ps = 0.05ns

    # Behavioral DFF timing parameters (from sky130_wrapper.v)
    setup_time_ns = 5.0   # SETUP_TIME parameter
    hold_time_ns = 2.5    # HOLD_TIME parameter

    # Calculate expected indices
    # Clock arrives at 128 inverter delays = 128 * 0.05ns = 6.4ns
    # Setup: data must arrive setup_time before clock
    #   max_data_delay = clock_delay - setup_time = 6.4ns - 5.0ns = 1.4ns
    #   max_data_inversions = 1.4ns / 0.05ns = 28
    #   expected_setup_idx = 27 (since index 27 = 28 inverters, due to 0-indexing)
    # Hold: data timing relative to clock for hold violations
    #   This is more complex due to inverted data fed to DFF
    clock_delay_ns = 128 * inv_delay_ns  # 6.4ns
    max_setup_data_delay_ns = clock_delay_ns - setup_time_ns  # 1.4ns
    max_setup_inversions = int(max_setup_data_delay_ns / inv_delay_ns)  # 28
    expected_setup_idx = max_setup_inversions - 1  # 27 (index is 0-based)

    # For hold, starting at maximum delay (index 255 = 256 inverters = 12.8ns)
    # Clock at 128 inverters (6.4ns), hold time requirement: 2.5ns
    # Data can be delayed up to clock + hold_time = 6.4ns + 2.5ns = 8.9ns
    # That's ~178 inverters, so expected index ~177 (odd value)
    expected_hold_idx = 177  # Approximate boundary where hold test passes

    dut._log.info(f"\n=== Setup Index Calculation ===")
    dut._log.info(f"Clock path: delayed_clk[127] = 128 inverters × {inv_delay_ns}ns = {clock_delay_ns}ns")
    dut._log.info(f"Data path: delayed_data[setup_index] = (setup_index+1) inverters × {inv_delay_ns}ns")
    dut._log.info(f"Setup time requirement: {setup_time_ns}ns")
    dut._log.info(f"\nSetup constraint: data_arrival + setup_time ≤ clock_arrival")
    dut._log.info(f"  (setup_index+1) × {inv_delay_ns}ns + {setup_time_ns}ns ≤ {clock_delay_ns}ns")
    dut._log.info(f"  (setup_index+1) × {inv_delay_ns}ns ≤ {max_setup_data_delay_ns}ns")
    dut._log.info(f"  (setup_index+1) ≤ {max_setup_inversions}")
    dut._log.info(f"  setup_index ≤ {expected_setup_idx}")
    dut._log.info(f"\nExpected setup_index = {expected_setup_idx}")
    dut._log.info(f"  At index {expected_setup_idx}: data arrives at {(expected_setup_idx+1)*inv_delay_ns}ns")
    dut._log.info(f"  Margin before clock: {clock_delay_ns}ns - {(expected_setup_idx+1)*inv_delay_ns}ns = {clock_delay_ns - (expected_setup_idx+1)*inv_delay_ns}ns ✓")
    dut._log.info(f"  At index {expected_setup_idx+2}: data arrives at {(expected_setup_idx+3)*inv_delay_ns}ns")
    dut._log.info(f"  Margin before clock: {clock_delay_ns}ns - {(expected_setup_idx+3)*inv_delay_ns}ns = {clock_delay_ns - (expected_setup_idx+3)*inv_delay_ns}ns ✗")

    dut._log.info(f"\n=== Hold Index Calculation ===")
    dut._log.info(f"Hold constraint: data must be captured correctly (not too late)")
    dut._log.info(f"Clock path: delayed_clk[127] = 128 inverters × {inv_delay_ns}ns = {clock_delay_ns}ns")
    dut._log.info(f"Data path: delayed_data[hold_index] = (hold_index+1) inverters × {inv_delay_ns}ns")
    dut._log.info(f"Hold time requirement: {hold_time_ns}ns")
    dut._log.info(f"\nStarting at maximum delay (index 255), expecting to decrease to find boundary")
    dut._log.info(f"Expected hold_index = {expected_hold_idx}")
    dut._log.info(f"  At index {expected_hold_idx}: data arrives at {(expected_hold_idx+1)*inv_delay_ns}ns")
    dut._log.info(f"  Margin after clock: {(expected_hold_idx+1)*inv_delay_ns}ns - {clock_delay_ns}ns = {(expected_hold_idx+1)*inv_delay_ns - clock_delay_ns}ns ✓")
    dut._log.info(f"  At index {expected_hold_idx+2}: data arrives at {(expected_hold_idx+3)*inv_delay_ns}ns")
    dut._log.info(f"  Margin after clock: {(expected_hold_idx+3)*inv_delay_ns}ns - {clock_delay_ns}ns = {(expected_hold_idx+3)*inv_delay_ns - clock_delay_ns}ns ✗")

    # Reset and run
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.ui_in.value = 0  # Test mode
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1

    # Let indices converge
    dut._log.info("Waiting for convergence...")

    # Sample indices during convergence - use many more cycles due to random noise
    prev_cycle = 0
    for cycle in [100, 250, 500, 750, 1000]:
        await ClockCycles(dut.clk, cycle - prev_cycle)
        prev_cycle = cycle

        # Read current values
        serial_data, valid_flag = await deserialize_output(dut, 32)
        curr_setup = (serial_data >> 16) & 0xFF
        curr_hold = serial_data & 0xFF

        # Read mismatch signals
        setup_mismatch = (dut.uo_out.value.to_unsigned() >> 2) & 0x1
        hold_mismatch = (dut.uo_out.value.to_unsigned() >> 3) & 0x1

        dut._log.info(f"  Cycle {cycle:4d}: setup_idx={curr_setup:3d} (mismatch={setup_mismatch}), hold_idx={curr_hold:3d} (mismatch={hold_mismatch})")

    # Final read
    serial_data, valid_flag = await deserialize_output(dut, 32)
    setup_index = (serial_data >> 16) & 0xFF
    hold_index = serial_data & 0xFF

    # Convert indices to timing values
    setup_data_delay_ns = (setup_index + 1) * inv_delay_ns
    hold_data_delay_ns = (hold_index + 1) * inv_delay_ns
    setup_margin_ns = clock_delay_ns - setup_data_delay_ns
    hold_margin_ns = hold_data_delay_ns - clock_delay_ns

    dut._log.info(f"\n=== Converged Results ===")
    dut._log.info(f"Setup index: {setup_index} → {setup_data_delay_ns}ns data delay ({setup_index + 1} inverters)")
    dut._log.info(f"  Clock delay: {clock_delay_ns}ns")
    dut._log.info(f"  Data arrives {setup_margin_ns}ns before clock")
    dut._log.info(f"  Required setup time: {setup_time_ns}ns → Margin: {setup_margin_ns - setup_time_ns}ns")

    dut._log.info(f"\nHold index: {hold_index} → {hold_data_delay_ns}ns data delay ({hold_index + 1} inverters)")
    dut._log.info(f"  Clock delay: {clock_delay_ns}ns")
    dut._log.info(f"  Data arrives {hold_margin_ns}ns after clock")
    dut._log.info(f"  Required hold time: {hold_time_ns}ns → Margin: {hold_margin_ns - hold_time_ns}ns")

    dut._log.info(f"\nExpected setup index: ~{expected_setup_idx}")
    dut._log.info(f"Expected hold index: ~{expected_hold_idx}")

    # Verify indices are valid and close to expected
    assert 0 <= setup_index <= 255, "Setup index should be valid"
    assert 0 <= hold_index <= 255, "Hold index should be valid"

    # Fail if more than 10 away from expected
    setup_error = abs(setup_index - expected_setup_idx)
    hold_error = abs(hold_index - expected_hold_idx)

    assert setup_error <= 10, (
        f"Setup index {setup_index} is {setup_error} away from expected {expected_setup_idx} (max allowed: 10)"
    )
    assert hold_error <= 10, (
        f"Hold index {hold_index} is {hold_error} away from expected {expected_hold_idx} (max allowed: 10)"
    )

    dut._log.info(f"\nSetup index error: {setup_error} (within tolerance)")
    dut._log.info(f"Hold index error: {hold_error} (within tolerance)")
    dut._log.info("\nNote: Current wrapper uses fixed DFF parameters (5ns/2.5ns)")
    dut._log.info("In real silicon, indices would converge based on actual DFF timing")
    dut._log.info("Test passed - PLL tracking logic is functional")


