---
description: Notarize a file or text into Bitcoin (free) and return a Forever Proof
argument-hint: [path or text to prove existed now]
---

Notarize the file or text in $ARGUMENTS so it can be proven to have existed at this moment.

Compute its SHA-256 locally, then call `sebbi_notarize` with the digest and `sebbi_forever_proof` for a proof anyone can check. Give the user the receipt and the verification link (https://sebbi.pro/forever).

Only the hash ever leaves the machine — never the content itself. If no file or text was given, ask what they want to prove.
