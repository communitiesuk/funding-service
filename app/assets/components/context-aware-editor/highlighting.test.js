import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { parseReferences } from "./highlighting.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixturePath = path.resolve(
    __dirname,
    "../../../../tests/fixtures/reference-regex-validation.json",
);
const cases = JSON.parse(readFileSync(fixturePath, "utf8"))["test_cases"];

describe("parseReferences (shared fixtures)", () => {
    test.each(cases)("$pattern", ({ pattern, references }) => {
        const matches = parseReferences(pattern).map((ref) => ref.match);
        expect(matches).toEqual(references);
    });
});
