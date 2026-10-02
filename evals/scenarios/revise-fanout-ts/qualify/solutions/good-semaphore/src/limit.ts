// A counting semaphore: at most `size` holders at a time, the rest wait in line in arrival order.

export class Semaphore {
  private free: number;
  private readonly waiting: Array<() => void> = [];

  constructor(size: number) {
    if (!Number.isInteger(size) || size < 1) throw new RangeError(`semaphore size ${size}`);
    this.free = size;
  }

  async acquire(): Promise<void> {
    if (this.free > 0) {
      this.free -= 1;
      return;
    }
    await new Promise<void>((resolve) => this.waiting.push(resolve));
  }

  release(): void {
    const next = this.waiting.shift();
    if (next) next();
    else this.free += 1;
  }

  /** Run fn while holding the semaphore. */
  async with<T>(fn: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await fn();
    } finally {
      this.release();
    }
  }
}
