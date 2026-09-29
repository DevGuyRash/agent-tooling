/**
 * Run tasks with at most `limit` of them running at once.
 *
 * A task is normally a function that starts a piece of async work and returns a
 * promise; a promise or plain value is also accepted and awaited as-is. Resolves
 * with the results in the same order as `tasks` and rejects with the first error.
 *
 * @template T
 * @param {Array<(() => Promise<T> | T) | Promise<T> | T>} tasks
 * @param {number} limit
 * @returns {Promise<T[]>}
 */
export async function runWithConcurrency(tasks, limit) {
  const results = new Array(tasks.length);
  let next = 0;

  async function worker() {
    while (next < tasks.length) {
      const index = next++;
      const task = tasks[index];
      results[index] = await (typeof task === 'function' ? task() : task);
    }
  }

  const workers = [];
  for (let i = 0; i < Math.min(limit, tasks.length); i++) {
    workers.push(worker());
  }
  await Promise.all(workers);
  return results;
}
