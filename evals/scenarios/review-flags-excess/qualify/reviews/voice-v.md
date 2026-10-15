Branch review - what I would say in person:

"The sort is the first thing. You have reverse=True on the tuple, and that flips names and ids too - R8 says A to Z. Then the notice total: you multiply the days by fifty instead of adding the fines, and the fines are capped and discounted, so the footer is simply wrong for those.

The rest is about size. I don't see why we have a registry and an abstract class for one fine rule, or four rounding modes when R7 says nearest, or a cache with a TTL in something that runs once. None of those is in the spec. I'd drop them.

I did stop on the retry and on the CSV flag because they looked like the same kind of thing, but they are both in the spec, so they are fine."
