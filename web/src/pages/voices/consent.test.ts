import { describe, expect, it } from "vitest";

import { consentProblems, EMPTY_CONSENT, type ConsentValues } from "./consent";

const signed: ConsentValues = {
  ...EMPTY_CONSENT,
  speaker: "Ada Lovelace",
  signature: "ada  lovelace",
  agree_clone: true,
  agree_ai_label: true,
  agree_withdraw: true,
};

describe("voice consent form", () => {
  it("accepts a complete form for your own voice", () => {
    expect(consentProblems(signed)).toEqual({});
  });
  it("needs every agreement and a matching signature", () => {
    const errors = consentProblems({
      ...signed,
      agree_withdraw: false,
      signature: "Someone Else",
    });
    expect(errors.agreements).toMatch(/all three/);
    expect(errors.signature).toMatch(/same name/);
  });
  it("needs a note of written permission for someone else's voice", () => {
    expect(
      consentProblems({ ...signed, relationship: "permission" })
        .permission_record,
    ).toBeTruthy();
    expect(
      consentProblems({
        ...signed,
        relationship: "permission",
        signature: "Charles",
        permission_record: "Signed form on file",
      }),
    ).toEqual({});
  });
});
