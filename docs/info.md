<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## 🔬 Setup/Hold Time Characterization with Delay Chains

This design characterizes the **setup and hold time** of flip-flops using configurable inverter delay chains. It automatically finds the minimum delay required to avoid timing violations using a PLL-style tracking algorithm, and outputs results via a continuous serial interface.

### How it Works 🧠

The design uses inverter delay chains to precisely measure flip-flop timing requirements:

1. **Delay Chain Architecture:**
   * **Clock delay chain:** 129-stage chain of Sky130 `inv_1` gates (delayed_clk[128:0])
   * **Data delay chain:** 257-stage chain of Sky130 `inv_1` gates (delayed_data[256:0])
   * Each inverter adds ~50ps delay (actual delay determined by process)
   * Configurable tap selection using 8-bit indices (setup_index, hold_index)

2. **PLL-Style Automatic Tracking:**
   * Both setup and hold tests use **fixed clock delay** (delayed_clk[127]) and **variable data delay**
   * **Setup Test:** Data delay varies via setup_index
     * Starts at minimum delay (1) where no violations occur (plenty of setup time)
     * Increments until violations appear
     * Converges to maximum data delay that avoids violations
   * **Hold Test:** Data delay varies via hold_index
     * Starts at maximum delay (255) where violations occur (insufficient hold time)
     * Decrements until violations stop
     * Converges to minimum data delay that avoids violations
   * Indices automatically converge to the violation boundary

3. **Continuous Serial Output:**
   * 32-bit frames shift out automatically every clock cycle (33 clocks per frame)
   * **Test Mode:** `{8'h0, setup_index[7:0], 8'h0, hold_index[7:0]}`
   * **Ring Osc Mode:** `{clk_ring_count[15:0], data_ring_count[15:0]}`
   * `SHIFT_VALID` pulses high on first bit of each frame

4. **Ring Oscillator Mode (ui_in[7]=1):**
   * **Clock ring:** 129-stage chain (odd number for oscillation)
   * **Data ring:** 257-stage chain (odd number for oscillation)
   * Counts oscillation frequency to measure inverter delay
   * Useful for process variation characterization

---

### Pin Configuration 📌

**Inputs:**
* `ui_in[7]` - MODE_SELECT: 0=setup/hold test, 1=ring oscillator
* `ui_in[6:0]` - Unused

**Outputs:**
* `uo_out[0]` - SERIAL_DATA: Continuous serial output (MSB first)
* `uo_out[1]` - SHIFT_VALID: High during first valid bit
* `uo_out[2]` - SETUP_MISMATCH: Setup violation detected
* `uo_out[3]` - HOLD_MISMATCH: Hold violation detected
* `uo_out[4]` - SETUP_DFF_OUT: Setup test flip-flop output
* `uo_out[5]` - HOLD_DFF_OUT: Hold test flip-flop output
* `uo_out[6]` - CLK_RING_OUT: Clock ring oscillator (ring osc mode)
* `uo_out[7]` - DATA_RING_OUT: Data ring oscillator (ring osc mode)

**Bidirectional (all outputs):**
* `uio_out[7:0]` - INDEX_MON: Current setup_index or clk_count lower bits

---

### How to Test 🧪

**Test Mode (Characterize Setup/Hold Times):**

**IMPORTANT:** Clock period must be longer than maximum delay chain length
- Clock delay chain: 129 inverters × ~50ps = ~6.45ns typical
- Data delay chain: 257 inverters × ~50ps = ~12.85ns typical
- **Minimum recommended clock period: 20ns (50MHz maximum)**
- If clock is too fast, delayed signals arrive after the next clock edge → incorrect measurements

1. **Setup:** Set `ui_in[7]=0` for test mode, connect clock to `clk` input (10-50MHz recommended)
2. **Wait for Convergence:** Allow ~500 clock cycles for indices to stabilize
3. **Read Serial Output:**
   * Monitor `SHIFT_VALID` (uo_out[1]) to detect frame start
   * Clock in 32 bits from `SERIAL_DATA` (uo_out[0])
   * Extract: setup_index = bits[23:16], hold_index = bits[7:0]
4. **Calculate Timing:**
   * Setup time ≈ setup_index × inverter_delay
   * Hold time ≈ hold_index × inverter_delay
   * Inverter delay ≈ 50ps typical (measure via ring osc mode)

**Ring Oscillator Mode (Measure Inverter Delay):**

1. **Setup:** Set `ui_in[7]=1` for ring oscillator mode
2. **Observe Outputs:** Watch CLK_RING_OUT and DATA_RING_OUT toggle
3. **Read Counts:** Serial output contains 32-bit frequency counts
4. **Calculate Delay:**
   * **Clock ring period** = 2 × 129 × inverter_delay (129 inversions for odd-number oscillation)
   * **Data ring period** = 2 × 257 × inverter_delay (257 inversions for odd-number oscillation)
   * Frequency = count / measurement_time
   * Inverter delay can be calculated from either ring frequency

**Debug Signals:**

* `SETUP_MISMATCH`/`HOLD_MISMATCH` show real-time violation status
* `INDEX_MON` on bidirectional pins shows current tracking values
* Waveform capture recommended for detailed analysis

---

### External Hardware 🔌

**Minimum Setup:**
* Clock source for `clk` input (10-50MHz recommended)
* Logic analyzer or microcontroller to read serial output

**Recommended Setup:**
* Clock generator with variable frequency
* Logic analyzer with protocol decoder for serial data
* Oscilloscope to view ring oscillator outputs
* LED indicators for mismatch flags

**Advanced Characterization:**
* Temperature chamber to measure timing vs. temperature
* Variable supply voltage to measure timing vs. VDD
* Multiple chips to characterize process variation

---

### Theory of Operation 📚

The design implements on-chip timing characterization by creating controlled setup/hold violations:

**Setup Time Violation:** Occurs when data arrives too late relative to clock, reducing the time data has to stabilize before being sampled. Both DFFs use a fixed clock delay (128 inverters = 6.4ns typical). The setup test varies data delay from minimum (index=1) to find the maximum data delay that still meets setup time requirements.

**Hold Time Violation:** Occurs when data arrives too early and changes too soon after the clock edge. The hold test varies data delay from maximum (index=255) down to find the minimum data delay that still meets hold time requirements.

By using long inverter chains with small delays, the design can measure timing with picosecond resolution, limited only by the inverter delay granularity (~50ps per inverter).

**Design Constraints:**
- Clock delay chain: 129 inverters total (tap at 128 for tests = ~6.4ns typical)
- Data delay chain: 257 inverters = ~12.85ns typical maximum
- Maximum data delay (~12.85ns typical) must be less than clock period
- If data delay > clock period, delayed data may arrive after next clock edge → incorrect measurements
- Recommended operating range: 10-50MHz (20ns-100ns period)
- Lower frequencies give more margin, higher frequencies test faster

---
