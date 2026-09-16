import { describe, expect, it } from "vitest";

import { displayDecimal } from "./decimal-display";

describe("exact source amount display", () => {
  it("preserves currency precision without floating point or fixed decimal rounding", () => {
    expect(displayDecimal("1.125000000000")).toBe("1.125");
    expect(displayDecimal("100.000000000000")).toBe("100");
    expect(displayDecimal("9007199254740993.123456789012")).toBe("9007199254740993.123456789012");
    expect(displayDecimal("-0.000000000001")).toBe("-0.000000000001");
    expect(displayDecimal("0.000000000000")).toBe("0");
    expect(displayDecimal(null)).toBe("—");
  });
});
