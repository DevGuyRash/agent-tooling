# Adds the feed command to the README's command list (shared by the qualification scripts).
set -e
sed -i 's/^node bin\/shop.ts check CATALOG                  load the catalog and count its products$/&\nnode bin\/shop.ts feed CATALOG [--countries ...]  product feed for price-comparison sites (docs\/feed.md)/' README.md
grep -q '^node bin/shop.ts feed' README.md
