# Evidential Undertaking

**AILeash — operated by Monop Content**
**Version 1.0 · 9 August 2026 · England & Wales**

Sealed into the AILeash chain on publication. The block index and receipt hash
for this document are printed at the foot and can be verified by anyone,
without an account and without our assistance.

---

## 1. Why this document exists

A hash chain is a technical artifact. It becomes evidence when someone is
willing to be held to what it says, in a forum where being wrong has
consequences.

Everything AILeash publishes about itself is currently a description. This
document converts the descriptions into undertakings: statements the operator
is bound by, capable of being breached, and fixed at a point in time that the
operator cannot move afterwards.

Nothing here asks anyone to trust us. It sets out what we are on the hook for,
what we are not, and how a third party checks both without our involvement.

---

## 2. What the chain proves

Precisely three things, and it is worth being exact because the market is not.

**Order.** Every sealed record carries the digest of the record before it. The
sequence in which events were committed is fixed and cannot be reordered
afterwards without breaking every subsequent link. Where a human decision was
committed before a machine verdict was revealed, the chain fixes that order
permanently.

**Integrity.** Any alteration to a sealed record changes its digest, which
breaks the chain from that point forward. Alteration is not prevented. It is
made evident.

**Completeness of what was sealed.** At the close of each period, every leaf
sealed in that period is sorted, a Merkle root is built over the sorted list,
and the root and the exact leaf count are committed and anchored. An export
from that period claiming a different total contradicts a number fixed before
anyone asked for it. Because the list is sorted, the absence of a record can be
proved by producing the two leaves it would have sorted between and
demonstrating that their indices are consecutive.

---

## 3. What the chain does not prove

Stated first-person, because a limitation buried in an appendix is a
limitation designed not to be read.

- **Not the truth of the contents.** A sealed record is a faithful record of
  what was submitted. If what was submitted was false, the chain preserves a
  false statement accurately.
- **Not anything about records that were never sealed.** A decision that never
  reached the chain is outside everything above. What changes is that the
  operator can no longer choose which of the sealed records to disclose.
- **Not the identity of the person behind an action** beyond the credential
  used. The chain evidences that a key acted, not who held it.
- **Not that the log existed when it says it did**, on the strength of the
  chain alone. Append-only structure is compatible with a log constructed
  yesterday. That is what external anchoring is for, and section 5 addresses
  the limits of ours.

---

## 4. Legal basis relied on

*The operator is not a law firm and this section is not legal advice. It sets
out the provisions relied on so that a party's own solicitor can test them.*

**Admissibility in civil proceedings.** The general rule against hearsay was
abolished in civil proceedings by section 1 of the Civil Evidence Act 1995.
Records forming part of a business's records may be proved by a certificate
under section 9 of that Act. The certificate at section 7 below is drafted for
that purpose.

**Machine-produced representations.** The statutory scheme formerly in section
69 of the Police and Criminal Evidence Act 1984 was repealed in 1999. In
criminal proceedings, section 129 of the Criminal Justice Act 2003 governs
representations made otherwise than by a person, and the common law presumption
that a mechanical instrument was working properly applies unless displaced.
Records of this kind are stronger where the mechanism's operation can be
independently reproduced, which is the purpose of the published verification
rules.

**Timestamps.** Under Article 41 of Regulation (EU) 910/2014 as retained in UK
law, a *qualified* electronic time stamp enjoys a presumption of the accuracy
of the date and time it indicates and of the integrity of the data it is
attached to. A non-qualified timestamp is not deprived of legal effect or
admissibility, but carries no presumption and must be proved.

**Accountability.** Article 5(2) UK GDPR requires a controller to be able to
demonstrate compliance. Evidence of the order in which a decision was reviewed
speaks directly to Article 22(3) where meaningful human review is relied on.

**Adoption by a witness.** No document produced by a system speaks for itself.
The certificate below is drafted to be adopted by a named individual with a
statement of truth under CPR Part 22, and, in the Business and Property Courts,
subject to Practice Direction 57AC for trial witness statements.

---

## 5. Anchoring: the current position, stated plainly

The chain tip is submitted to OpenTimestamps and upgraded to a Bitcoin
attestation once confirmed. This is a genuinely independent authority the
operator cannot influence, and it is technically robust.

It is **not** a qualified electronic time stamp within the meaning of Article
41. It therefore carries no statutory presumption, and a party relying on it in
proceedings would have to prove the timing rather than assert it.

The operator undertakes to add a qualified electronic time stamp from a
qualified trust service provider, in parallel with and not in place of the
existing anchor, and to publish the provider's identity. Until that is live,
this section is the disclosure of the gap rather than an account of a solved
problem.

Two anchors answer two different questions. The qualified timestamp gives legal
presumption. The Bitcoin anchor gives an authority that no trust service
provider, regulator, or government can retrospectively instruct. A party that
needs both should have both.

---

## 6. The undertakings

Each is tied to an endpoint that any person may call without an account and
without notifying us. A published check that cannot be run by a stranger is
marketing, and is marked as such in our discovery document rather than counted.

1. **We will not withdraw a published check silently.** The discovery document
   at `/.well-known/ordering-test.json` is sealed on every material change, and
   the history is retrievable. A check that becomes unsupported will say so.

2. **We will not mark a check publicly demonstrable unless a stranger can
   demonstrate it.** Where a capability exists but requires a key, it is
   published as supported and not publicly demonstrable. We accept that this
   lowers our own score.

3. **We will commit each closed period.** Commitment is automatic and
   deployment-wide. Where a period was committed late, the delay in days is
   published against that period rather than smoothed over.

4. **We will not recommit a period.** A period is committed once. A second
   attempt returns the existing commitment.

5. **We will publish gaps.** A period that was never committed is visible as an
   absence in the period list. We will not backfill silently to close a gap
   that an auditor has already seen.

6. **We will answer an absence request against a fixed root.** Any person may
   ask whether a key was sealed in a committed period and receive a proof that
   verifies against a root committed before the question was asked.

7. **We will not require our own tooling for verification.** The hashing rules
   are published at `/x/complete/spec` in sufficient detail to write an
   independent verifier. A proof that can only be checked with the prover's
   tool is not a proof.

**Consequence of breach.** Where a party has entered into a written agreement
with the operator, breach of any undertaking in this section is a breach of
that agreement, and the party may terminate for material breach and require
delivery of the full sealed record for every period in scope. Where no such
agreement exists, this document stands as a public representation as to the
operation of the service, on which reliance is intended and foreseeable.

---

## 7. Certificate of evidence

*Template. To be completed and adopted by a named individual. The system
produces the values; only a person can adopt them.*

> **Certificate as to records produced by the AILeash chain**
>
> I, [full name], of [address], [position] at [entity], state as follows.
>
> 1. I am authorised to make this certificate on behalf of [entity]. The facts
>    stated are within my own knowledge or drawn from records held by [entity]
>    in the course of its business, and are true.
>
> 2. The records exhibited at [exhibit reference] were produced from the
>    AILeash chain operated at [domain] and comprise [number] sealed records
>    covering the period [start] to [end].
>
> 3. The period [period] was committed on [commit date], being [n] days after
>    the period closed. The committed Merkle root is [root] and the sealed leaf
>    count is [count]. That commitment is recorded in the chain at block index
>    [index] with receipt hash [hash].
>
> 4. The chain tip covering that commitment was submitted to [anchor
>    authority] on [date] and the attestation status at the date of this
>    certificate is [status].
>
> 5. The number of records exhibited is [number], which [accords with / differs
>    from] the sealed leaf count. [Where it differs, explain.]
>
> 6. The verification rules applied are those published at [domain]/x/complete/spec
>    as at [date]. I am not aware of any matter affecting the reliability of the
>    records, or of any respect in which the system was not operating properly
>    during the period covered.
>
> **Statement of truth**
> I believe that the facts stated in this certificate are true. I understand
> that proceedings for contempt of court may be brought against anyone who
> makes, or causes to be made, a false statement in a document verified by a
> statement of truth without an honest belief in its truth.
>
> Signed: ......................  Date: ......................

Paragraph 5 is the paragraph that matters, and it is deliberately the hardest
one to complete dishonestly. A person signing a statement of truth must
reconcile the number of records they are handing over against a number that was
sealed and anchored before anybody asked for them.

---

## 8. This document is itself sealed

The undertakings above are committed to the chain they describe. The terms the
operator is bound by are therefore fixed at a point in time and cannot be
quietly revised. A future version will be sealed as a new record; the earlier
version remains retrievable and its receipt remains valid.

Any party may verify that the version they were shown is the version that was
sealed, by comparing the digest of the document they hold against the sealed
record.

    Document version   1.0
    Sealed at          [block index]
    Receipt hash       [hash]
    Document digest    [sha256 of this file, UTF-8, as published]
    Anchored           [anchor status at publication]

---

## 9. Standing limits

- This is one operator's undertaking about one operator's system. It is not a
  cross-vendor standard and does not claim to be. Where a joint conformance
  test is agreed with another operator, it will be published separately and
  identified as joint.
- The qualified timestamp described at section 5 is not yet live. Until it is,
  timing must be proved rather than presumed.
- Nothing in this document is legal advice, and a party intending to rely on
  these records in proceedings should take its own advice on admissibility in
  the relevant jurisdiction and forum.
- The operator is a single-person business. Continuity of the service is
  addressed in the applicable agreement, not here. A party whose evidential
  position depends on this chain should hold its own copy of every receipt it
  may need, and is entitled to export them at any time.
