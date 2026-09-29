// node --test reporter (check harness): one JSON line per finished test, so two runs of the same
// suite can be compared test by test.
export default async function* reporter(source) {
  for await (const event of source) {
    if (event.type !== 'test:pass' && event.type !== 'test:fail') continue;
    const { name, nesting, file, skip, todo } = event.data;
    yield `${JSON.stringify({
      status: event.type === 'test:pass' ? 'pass' : 'fail',
      name,
      nesting,
      file: file ?? null,
      skip: Boolean(skip),
      todo: Boolean(todo),
    })}\n`;
  }
}
