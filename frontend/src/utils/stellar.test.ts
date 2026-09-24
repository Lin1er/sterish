import { describe, expect, it } from "vitest";

import { isAccountAddress } from "./stellar";

describe("isAccountAddress", () => {
  it("accepts a classic G account", () => {
    expect(
      isAccountAddress(
        "GDAVKROBU6VGWMAY36YMHQ6LV7XD7D5R5T3LJTTEBJKX3EURZAEDHSPL",
      ),
    ).toBe(true);
  });

  it("refuses what cannot hold a licence", () => {
    // Contract and muxed addresses, and anything of the wrong shape.
    expect(
      isAccountAddress("CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T"),
    ).toBe(false);
    expect(
      isAccountAddress(
        "MDAVKROBU6VGWMAY36YMHQ6LV7XD7D5R5T3LJTTEBJKX3EURZAEDHSPLAAAAAAAAAAAAA",
      ),
    ).toBe(false);
    expect(
      isAccountAddress(
        "gdavkrobu6vgwmay36ymhq6lv7xd7d5r5t3ljtteBJKX3EURZAEDHSPL",
      ),
    ).toBe(false);
    expect(isAccountAddress("G")).toBe(false);
    expect(isAccountAddress("")).toBe(false);
  });
});
