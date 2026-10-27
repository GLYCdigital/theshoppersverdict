---
title: "Corrections"
description: "What we got wrong, when we found out, and what changed."
type: page
---

## 27 October 2026 — Review counts and Amazon star ratings

**What was wrong.** Review pages displayed a review count and an "on Amazon" star
rating that were not read from Amazon. The count was generated from a template
formula keyed to the star rating, and on many pages the rating mirrored our own
verdict score. Those numbers were also published as machine-readable
`AggregateRating` structured data, which is how they reached search results.

**How we found it.** While correcting a smaller display bug on 13 pages, we checked
where the review count came from and found it was derived rather than observed.
Across roughly 25,800 review pages, eight count values accounted for about 89% of
the site.

**What changed on 27 October 2026.**
- Star ratings and review counts are now published as `AggregateRating` only when
  we hold an actual observation for that product — a recorded count and the date it
  was observed, no older than 90 days. Nothing is estimated or inferred.
- Pages without that record no longer present a number as Amazon's. They show our
  own verdict instead, labelled as ours.
- Our product-verdict generation now rejects new content that carries a review count
  without an observation behind it.

**What this means for you.** Where a page shows "Our verdict", that score is our
editorial assessment from reading the product's reviews — it is not an Amazon
average, and we no longer imply that it is. Amazon ratings will reappear on pages as
we re-observe them, with the observation date attached.

We would rather show fewer stars than show numbers we cannot stand behind.
