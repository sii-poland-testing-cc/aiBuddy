import { describe, it, expect } from "vitest";
import { parseRelatedTerms } from "../lib/parseRelatedTerms";
import type { GlossaryTerm } from "../components/Glossary";

const GLOSSARY: GlossaryTerm[] = [
  { term: "Settlement", definition: "Transfer of funds.", related_terms: [] },
  { term: "Reconciliation", definition: "Matching of records.", related_terms: [] },
];

describe("parseRelatedTerms", () => {
  it("test_known_terms_marked_as_glossary", () => {
    const chunks = parseRelatedTerms("Settlement, Reconciliation, UnknownTerm", GLOSSARY);
    expect(chunks).toHaveLength(3);
    expect(chunks[0].isGlossaryTerm).toBe(true);
    expect(chunks[0].glossaryItem?.term).toBe("Settlement");
    expect(chunks[1].isGlossaryTerm).toBe(true);
    expect(chunks[1].glossaryItem?.term).toBe("Reconciliation");
    expect(chunks[2].isGlossaryTerm).toBe(false);
    expect(chunks[2].glossaryItem).toBeUndefined();
  });

  it("test_case_insensitive_match", () => {
    const chunks = parseRelatedTerms("settlement", GLOSSARY);
    expect(chunks).toHaveLength(1);
    expect(chunks[0].isGlossaryTerm).toBe(true);
    expect(chunks[0].glossaryItem?.term).toBe("Settlement");
  });

  it("test_empty_input", () => {
    const chunks = parseRelatedTerms("", GLOSSARY);
    expect(chunks).toHaveLength(0);
  });
});
