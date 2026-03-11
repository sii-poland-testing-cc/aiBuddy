import type { GlossaryTerm } from "@/components/Glossary";

export interface TermChunk {
  text: string;
  isGlossaryTerm: boolean;
  glossaryItem?: GlossaryTerm;
}

export function parseRelatedTerms(
  sectionText: string,
  glossary: GlossaryTerm[],
): TermChunk[] {
  const terms = sectionText.split(",").map((t) => t.trim()).filter(Boolean);
  return terms.map((text) => {
    const match = glossary.find(
      (g) => g.term.toLowerCase() === text.toLowerCase(),
    );
    return { text, isGlossaryTerm: !!match, glossaryItem: match };
  });
}
