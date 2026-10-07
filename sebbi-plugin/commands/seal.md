---
description: Score and seal an AI decision into the sebbi.pro chain, timestamped into Bitcoin
argument-hint: [the decision, e.g. "refund £120 for customer-42"]
---

Seal the decision described in $ARGUMENTS using the connected `sebbi` tools. If no details were given, ask what the decision is (who it is about, what action, any amount).

Score it with the sebbi decision flow (`sebbi_test_decision` or the govern tool) to get a verdict — ALLOW, CHALLENGE or BLOCK — then confirm it is sealed. Give the user the block index and the link to verify it, and explain the verdict in one line. The record is now permanent and checkable by anyone against Bitcoin.
