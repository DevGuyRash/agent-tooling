/**
 * Parse the catalog export: one SKU per line, ignoring blank lines and `#` comments.
 *
 * @param {string} text
 * @returns {string[]}
 */
export function parseSkuList(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== '' && !line.startsWith('#'));
}
