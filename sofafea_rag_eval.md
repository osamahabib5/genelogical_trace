# SOFAFEA RAG Evaluation Set
## 2023 Journal — Volume II

> **Purpose:** Test a RAG chatbot pipeline against the 2023 SOFAFEA Journal.  
> Questions are grouped by type to stress different retrieval and reasoning behaviors.
> Each entry includes the question, the gold-standard answer, the source passage(s) needed, and notes on failure modes to watch for.

---

## Category 1: Factual Recall (Single-Chunk Retrieval)

These test whether the correct chunk is retrieved and basic facts are accurately quoted.

---

**Q1.** What is the SOFAFEA membership cutoff date, and what historical event defines it?

**Answer:** March 5, 1770 — the date of the Boston Massacre and the death of Crispus Attucks, the first patriot casualty of the American Revolution.

**Source:** Mission Statement / Membership Eligibility section.

**Watch for:** The model citing only the Boston Massacre without naming Crispus Attucks, or vice versa. Both are required for a complete answer.

---

**Q2.** What role did Caesar Russell serve in Captain William North's company?

**Answer:** Caesar Russell served as "personal servant to Capt. North." His duties included cleaning and laying out North's uniforms, emptying the chamber pot, stoking the fireplace, and preparing meals. He may also have coiffed North's hair and carried personal messages to other officers.

**Source:** "Fused Legacies" article — "Life After the War" and revolutionary war sections.

**Watch for:** The model answering only "personal servant" without including the specific listed duties, which are in the document.

---

**Q3.** What ship did Caesar Russell sail on to Calcutta, and when did it depart?

**Answer:** The Friendship of Salem (a full-rigged ship, Tonnage 342). It departed on March 6 or 8, 1806 from Salem. (Two sources give slightly different departure dates.)

**Source:** Chart 1 in the "Fused Legacies" article.

**Watch for:** The model citing only one date without noting the discrepancy, or confusing this with another voyage (e.g., the Anson voyage to the West Indies).

---

**Q4.** Where was Tobias Hill born, and on what date?

**Answer:** Tobias Hill was born on November 18, 1743, in Georgetown, York County, Maine (then part of the District of Maine, Massachusetts).

**Source:** "Maine's Tobias Hill" article — Generation 1 entry and the Georgetown vital records table.

**Watch for:** Confusing "Georgetown, Maine" with other Georgetowns, or omitting the county/year.

---

**Q5.** What did the 1860 New Bedford newspaper article say about Caesar Russell's age?

**Answer:** The Daily Evening Standard (August 17, 1860) reported that Caesar Russell was 112 years old, "as is proved by his original bill of sale as a slave."

**Source:** "Fused Legacies" article, section on identifying the man in Massachusetts.

**Watch for:** The model stating his age as 105 or 110 (from death records) rather than 112 (from the 1860 article). These are different claims in the document.

---

**Q6.** What was Samuel Harrison's occupation in relation to Robert Carter III?

**Answer:** Samuel Harrison served as Robert Carter III's barber, personal valet, and "waiting man." He tended to Carter's grooming (shaving, cutting hair, preparing wigs), managed his daily attire, and accompanied him on personal and official matters.

**Source:** "Sam Harrison & the Tobacco Planter" — First Generation entry.

**Watch for:** The model omitting "barber" and only saying "valet," or vice versa.

---

**Q7.** On what date were Samuel and Judith Harrison emancipated, and through what legal instrument?

**Answer:** January 1, 1793, through a "Deed of Gift" composed by Robert Carter III. The document was submitted and recorded at the Northumberland County courthouse on September 5, 1791.

**Source:** "Sam Harrison" article — First Generation, emancipation section.

**Watch for:** Conflating the recording date (1791) with the emancipation date (1793). Both dates appear in the document and are distinct.

---

## Category 2: Multi-Hop / Inference Questions

These require connecting information across two or more passages or sections.

---

**Q8.** How are Caesar Russell and Benjamin D. Brooker connected through their children?

**Answer:** Two of Caesar Russell's daughters — Olive ("Olley") Russell and Philinda Russell — married two sons of Benjamin D. Brooker (aka Benjamin Cain). Olive married Benjamin D. Brooker Junior in 1815; Philinda married Samuel Stanley Bruker (Brooker) in 1818. This makes Caesar Russell and Benjamin D. Brooker the grandfathers of the same generation of Brooker children.

**Source:** "Fused Legacies" — Second Generation entries for Olive and Philinda.

**Watch for:** The model reversing the relationship (saying Brooker's daughters married Russell's sons) or identifying only one of the two marriages.

---

**Q9.** Tobias Hill purchased land in what year, and how many years after the start of American Independence does the deed describe this as occurring?

**Answer:** The deed is dated "the Thirtieth day of March & the Fifth year of American Independence 1781." The fifth year of American Independence counts from 1776, confirming the 1781 date. Tobias purchased 40 acres in East Brunswick, Maine.

**Source:** "Maine's Tobias Hill" — section on land deed after the Revolutionary War.

**Watch for:** The model not connecting "Fifth year of American Independence" to the year 1781, or confusing East Brunswick with Georgetown.

---

**Q10.** What evidence does the article use to argue that Caesar Russell died in 1861, not 1862?

**Answer:** Three pieces of evidence: (1) His Last Will and Testament was filed in Bristol County probate court on November 8, 1861, and the estate was settled by August 25, 1862 — meaning he must have died before the will was filed; (2) At least ten obituaries were published within two weeks of his death in October 1861; (3) One of the death records stating 1862 is shown to contain other known 1861 deaths incorrectly listed as 1862, suggesting a clerical error by registrar James M. Cushman.

**Source:** "Fused Legacies" — section on Caesar's four death records.

**Watch for:** The model citing only one or two of the three pieces of evidence, or stating 1862 is possible.

---

**Q11.** What was Robert Carter III's religious journey, and how did Samuel Harrison participate in it?

**Answer:** Carter began as an Anglican/Episcopalian, then explored Methodist, Presbyterian, and Baptist faiths after a near-death smallpox experience in 1777. He formally joined the Morattico Baptist Church in March 1778 — and Samuel Harrison joined alongside him, the two worshipping side by side. By 1790, Carter had converted to the Church of the New Jerusalem (Swedenborgianism), which he considered the "True Christian Religion."

**Source:** "Sam Harrison" — spiritual journey section of First Generation.

**Watch for:** The model omitting Harrison's co-participation at the Baptist church, or not noting the final Swedenborgian conversion.

---

## Category 3: Ambiguity / Conflicting Information

These test whether the bot correctly surfaces documented uncertainty rather than hallucinating a definitive answer.

---

**Q12.** What year was Caesar Russell born?

**Answer:** The document presents two competing estimates and does not resolve the question definitively. If born c1748 (implied by the 1860 newspaper reporting his age as 112), he would have been ~33 at enlistment and died at ~113. If born c1765 (implied by the military enlistment document listing him as age 16), he would have died at ~96. The article concludes that both remain plausible and the question is unresolved pending new evidence.

**Source:** "Fused Legacies" — extensive section on birth year discrepancies.

**Watch for:** The model collapsing to a single birth year (1748 or 1765) without surfacing the ambiguity. This is a key test of whether the RAG system can reflect genuine uncertainty from the source document.

---

**Q13.** Did Caesar Russell marry Juda Cakenahew?

**Answer:** Uncertain. There are five index entries and two handwritten records documenting a marriage between a man named "Ceasor/Caesar Russell" and "Juda Cakenahew/Canahew" in Dartmouth, Massachusetts, in October 1765. However, if Caesar was born c1765, he could not have been this groom. If born c1748, he could have been ~17 at the time. The article states: "It remains uncertain whether our man married Juda."

**Source:** "Fused Legacies" — marriage records section.

**Watch for:** The model stating definitively that he did or did not marry Juda, rather than conveying the documented uncertainty.

---

**Q14.** Was Tobias Hill's brother Richard Hill the same person as Richard Denny in Revolutionary War records?

**Answer:** Possibly, but not definitively established. The article notes that Tobias's brother Dick (born 1747) was sold to Daniel Denny in 1752, later willed to Samuel Denny's son, and there are Revolutionary War records for both "Richard Hill" and "Richard Denny" in Leicester, Worcester, MA — both identified as "Negro," both serving in similar units (Capt. Brown's Company, Col. Jackson's Regiment). The Massachusetts State Archive noted significant overlap. However, the article states: "we are too early in the research to make a definitive statement."

**Source:** "Maine's Tobias Hill" — Revolutionary War Service section.

**Watch for:** The model asserting they are the same person as a fact.

---

## Category 4: List / Enumeration Questions

These test whether retrieval captures complete lists rather than partial ones.

---

**Q15.** Name the merchant ships Caesar Russell is documented to have sailed on, with their destinations.

**Answer (from Chart 1):**
1. Mary (Ship) — East Indies (Oct 1796, Beverly)
2. Mary (Ship) — Genoa, Italy (Nov 1801, Beverly)
3. Anson (Schooner) — West Indies (Mar 1805, Beverly)
4. Friendship of Salem (Ship) — Calcutta, India (Mar 1806, Salem)
5. Wells (Ship) — Copenhagen, Denmark (Mar 1807, Salem)
6. Augusta (Brigantine) — Havana, Cuba (Dec 1811)

**Source:** "Fused Legacies" — Chart 1.

**Watch for:** The model listing only 4–5 ships, or conflating two voyages on the Mary as one.

---

**Q16.** List the three criteria a colonial ancestor must meet to qualify for SOFAFEA membership.

**Answer:**
1. Can be documented by name in an accepted colonial record (land patent, court order, deed, will, birth/marriage/death certificate, military record, etc.) — NOTE: serving in the Revolutionary War alone does NOT qualify.
2. Can be found by name in a widely accepted book of abstracts for the designated colonial period.
3. Is previously proven by prior applicants, with proof of direct lineal descent from a previously qualified ancestor.

**Source:** Membership Eligibility section (appears twice in the document).

**Watch for:** The model omitting the important caveat that Revolutionary War service alone does not qualify an ancestor, or listing only two of the three criteria.

---

**Q17.** Which of Tobias Hill's grandsons served in the Civil War, and in what units?

**Answer (from the article):**
- Joseph Stewart Hill — U.S. Colored Troops 43rd Infantry, promoted to Comm Sergeant; African American Civil War Memorial Plaque C-57.
- Tobias Jefferson Hill — African American Civil War Sailor; Memorial Plaque A-7.
- William H Hill — Civil War Soldier, Coast Guard.
- James F Hill — 31st Regiment, United States Colored Infantry; Memorial Plaque B-47.

**Source:** "Maine's Tobias Hill" — legacy section and Generation entries.

**Watch for:** The model listing only 2–3 of the 4, or confusing their units.

---

## Category 5: Out-of-Scope / Unanswerable Questions

These test whether the bot correctly declines to answer questions the document cannot address.

---

**Q18.** What was the exact location of Crispus Attucks's birth?

**Expected behavior:** The document only refers to Crispus Attucks as the first patriot casualty of the Boston Massacre (March 5, 1770) — it does not provide his birthplace. The bot should say this information is not in the document and avoid hallucinating a location.

---

**Q19.** How many total enslaved people did Robert Carter III free under his Deed of Emancipation?

**Answer:** The article states Carter documented "452 of his slaves" in the official public document, but elsewhere states the emancipation covered "over 511 enslaved individuals and their descendants." Both figures appear in the document. The bot should surface both numbers and note they refer to different counts (the initial list vs. the total freed including descendants).

**Source:** "Sam Harrison" — emancipation section.

**Watch for:** The model citing only 452 or only 511 without noting both figures appear.

---

**Q20.** What is the SOFAFEA journal's ISSN number?

**Expected behavior:** The document provides an ISBN (9798844069628) but no ISSN. The bot should either provide the ISBN and note it is not an ISSN, or state that the ISSN is not in the document. It should not fabricate a number.

---

## Category 6: Genealogy-Specific Edge Cases

These are tricky questions that require careful reading of the genealogical entries.

---

**Q21.** Caesar Russell's Last Will named certain children but intentionally excluded others. Who was excluded and why?

**Answer:** Caesar's Last Will (dated August 21, 1861) left the bulk of his estate to his wife Lucretia ("Lutitia"), daughter Nancy, and sons Jesse and James. He explicitly wrote that his "four other children — viz: Sally, Betsey, Abby, and Reuben, also my grandchildren went not forgotten by me, but omitted as devises intentionally." No explanation accompanied the exclusions.

**Source:** "Fused Legacies" — final section on Caesar's estate.

**Watch for:** The model stating he forgot them or that the reason is known, when the document explicitly says no explanation was given.

---

**Q22.** What is the relationship between Harriet Granderson Brooker and Caesar Russell?

**Answer:** Harriet Granderson Brooker is Caesar Russell's granddaughter. Her mother, Philinda Russell, is Caesar's daughter. Philinda married Samuel Stanley Bruker (Brooker), and their daughter Harriet was born in 1817.

**Source:** "Fused Legacies" — Generations 1–3.

**Watch for:** The model saying "great-granddaughter" or confusing which Brooker line she belongs to.

---

**Q23.** Samuel Harrison 2nd is described as the "first descendant of Sam the barber to be born into freedom on American soil." Why is this significant?

**Answer:** Samuel Harrison (the original enslaved barber) and his wife Judith were not freed until January 1, 1793, and their son Henry was born enslaved around 1780 and freed in 1801 after completing an apprenticeship. Samuel Harrison 2nd, born free around 1807 in Westmoreland County, Virginia, is therefore the first of Samuel's line to be born already free — representing a generational transition from slavery to freedom that the article frames as a pivotal milestone in African American history.

**Source:** "Sam Harrison" — Third Generation entry.

**Watch for:** The model confusing Henry Harrison (freed 1801, born enslaved) with Samuel Harrison 2nd (born free 1807).

---

## Scoring Rubric (Suggested)

| Score | Criteria |
|-------|----------|
| 2 | Complete and accurate; ambiguity/uncertainty correctly surfaced where applicable |
| 1 | Partially correct; key details missing or minor factual error |
| 0 | Incorrect, hallucinated, or refuses to answer an answerable question |

**Priority failure modes to log:**
- Hallucinated dates or names not in the document
- Collapsing documented ambiguity into a false certainty (especially Q12, Q13, Q14)
- Partial list retrieval (especially Q15, Q17)
- Confusing similar names across genealogical generations (Q22, Q23)
- Citing the wrong date when two conflicting dates appear (Q7, Q10)

