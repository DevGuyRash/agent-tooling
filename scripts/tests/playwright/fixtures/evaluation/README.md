# Evaluation applications

These synthetic applications support the Playwright plugin's bounded comparative evaluation. They are repository test fixtures and are not shipped in the plugin. Each server instance has its own inventory, sessions, receipts, listener, delayed responses, and request log.

```js
import { startEvaluationServer } from './server.mjs';
const fixture = await startEvaluationServer({ scenario: 'site-survey', logPath: '/owned/output/requests.jsonl' });
try {
  console.log(fixture.origin);
  // The participant exercises the assigned local application.
  console.log(fixture.snapshot());
} finally {
  await fixture.close();
}
```

Executable mode prints the bound origin and keeps the server alive until SIGINT or SIGTERM: `node server.mjs site-survey --log /owned/output/requests.jsonl`. The other scenarios are `dashboard` and `quiet-checkout`. The server binds to loopback, allocates an available port by default, and refuses to overwrite an existing log. Request records include method, pathname, and the recognized day/team query values; authentication headers, login bodies, session tokens, and arbitrary query parameters are not logged. `snapshot()` is an observation interface for the controller, not a verdict on browser evidence.

Copy only `packets/<scenario>/` into a participant's assigned input workspace, adding the origin, output path, installed Playwright path, and condition materials. For checkout, participants need a writable copy of `checkout.test.mjs`; preserve the supplied `quiet-launch.mjs` launch preflight. Supply the original host display value as `EVAL_PRIMARY_DISPLAY` before any display wrapper changes the child's environment. Treat packet isolation as an instructed boundary unless the host actually enforces it.

Application implementation and server logs are controller resources. Expected findings, qualified evaluator checks, and execution records live under the repository's local context evaluation directory and are not participant inputs. The participant tasks leave exploration, capture composition, and output expression to the executor.
