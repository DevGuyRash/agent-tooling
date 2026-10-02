# Product feed for idealo and Google Shopping

Both comparison sites read a tab-separated product feed with what shipping costs to each country we list in. We'll upload the file by hand to start with, so a command that prints it is all we need. idealo compares the feed with what our checkout actually charges and takes listings down when they disagree.

The command:

```
node bin/shop.ts feed CATALOG [--countries CC,CC,...]
```

It prints a header line and then one line per active product and country: products in catalog order, and for each product the countries in the order given. `--countries` takes two-letter country codes in capitals, separated by commas; without it the countries are DE,AT,CH.

| column     | value |
|------------|-------|
| `sku`      | the product's SKU |
| `title`    | the catalog title |
| `price`    | the product's price |
| `country`  | the country code |
| `shipping` | what a customer in that country pays for shipping at checkout when they order just this product, one of it (`0.00` when that order ships free) |

Amounts have two decimals and a dot, no currency sign. Inactive products are left out. (Nothing we sell comes near the 10 kg parcel limit on its own, so every line has a shipping cost.)

Errors work like `quote`: a catalog that can't be read or isn't valid prints `shop: ...` on standard error and exits with status 1; a missing CATALOG, an unknown option, or a country code that isn't two capital letters is a usage error, exit status 2.

For `data/catalog.json` with the default countries:

```
$ node bin/shop.ts feed data/catalog.json
sku	title	price	country	shipping
SEN-100	Sencha Fukamushi, 100 g	11.50	DE	4.49
SEN-100	Sencha Fukamushi, 100 g	11.50	AT	9.90
SEN-100	Sencha Fukamushi, 100 g	11.50	CH	15.90
SEN-250	Sencha Fukamushi, 250 g	24.50	DE	5.49
SEN-250	Sencha Fukamushi, 250 g	24.50	AT	12.90
SEN-250	Sencha Fukamushi, 250 g	24.50	CH	21.90
GYO-50	Gyokuro Asahi, 50 g tin	18.50	DE	4.49
GYO-50	Gyokuro Asahi, 50 g tin	18.50	AT	9.90
GYO-50	Gyokuro Asahi, 50 g tin	18.50	CH	15.90
MAT-30	Matcha Uji, ceremonial grade, 30 g	22.00	DE	4.49
MAT-30	Matcha Uji, ceremonial grade, 30 g	22.00	AT	9.90
MAT-30	Matcha Uji, ceremonial grade, 30 g	22.00	CH	15.90
HOJ-100	Hojicha, 100 g	8.50	DE	4.49
HOJ-100	Hojicha, 100 g	8.50	AT	9.90
HOJ-100	Hojicha, 100 g	8.50	CH	15.90
GEN-1K	Genmaicha, 1 kg café bag	17.50	DE	6.49
GEN-1K	Genmaicha, 1 kg café bag	17.50	AT	16.90
GEN-1K	Genmaicha, 1 kg café bag	17.50	CH	29.90
KYU-BIZEN	Kyusu teapot, Bizen clay, 350 ml	54.00	DE	0.00
KYU-BIZEN	Kyusu teapot, Bizen clay, 350 ml	54.00	AT	12.90
KYU-BIZEN	Kyusu teapot, Bizen clay, 350 ml	54.00	CH	21.90
SET-GIFT	Discovery set, 6 tins	46.00	DE	5.49
SET-GIFT	Discovery set, 6 tins	46.00	AT	12.90
SET-GIFT	Discovery set, 6 tins	46.00	CH	21.90
CHA-WHISK	Chasen, bamboo whisk	26.00	DE	4.49
CHA-WHISK	Chasen, bamboo whisk	26.00	AT	9.90
CHA-WHISK	Chasen, bamboo whisk	26.00	CH	15.90
SAMPLE-5	Sample box, 5 x 10 g	6.90	DE	4.49
SAMPLE-5	Sample box, 5 x 10 g	6.90	AT	9.90
SAMPLE-5	Sample box, 5 x 10 g	6.90	CH	15.90
TET-KETTLE	Tetsubin kettle, cast iron, 1.2 l	89.00	DE	0.00
TET-KETTLE	Tetsubin kettle, cast iron, 1.2 l	89.00	AT	23.90
TET-KETTLE	Tetsubin kettle, cast iron, 1.2 l	89.00	CH	44.90
```

(The columns are separated by single tabs.)

-- Jonas
