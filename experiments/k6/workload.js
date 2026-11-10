import http from 'k6/http';
import { sleep } from 'k6';
import exec from 'k6/execution';

const brands = ['a', 'b', 'c'];
const seconds = Number(__ENV.DURATION_SECONDS);
const vus = Number(__ENV.VUS_PER_BRAND);
const idle = __ENV.SCENARIO === 'idle';

export const options = {
  discardResponseBodies: true,
  scenarios: idle ? {
    idle: { executor: 'shared-iterations', vus: 1, iterations: 1, maxDuration: `${seconds + 10}s`, exec: 'idleWindow' },
  } : Object.fromEntries(brands.filter(b => Number(__ENV[`RATE_${b.toUpperCase()}`]) > 0).map(b => {
    const suffix = b.toUpperCase();
    return [`brand_${b}`, {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV[`RATE_${suffix}`]),
      timeUnit: '1s',
      duration: `${seconds}s`,
      preAllocatedVUs: vus,
      maxVUs: vus,
      gracefulStop: '6s',
      tags: { tenant: `brand_${b}` },
      env: { BRAND: suffix },
    }];
  })),
};

export function idleWindow() {
  sleep(seconds);
}

export default function () {
  const brand = __ENV.BRAND;
  const iteration = exec.scenario.iterationInTest;
  const order = (iteration * 37) % 100 < Number(__ENV[`ORDER_PERCENT_${brand}`]);
  const headers = { Authorization: `Bearer ${__ENV[`K6_TOKEN_${brand}`]}` };
  if (order) {
    headers['Content-Type'] = 'application/json';
    headers['Idempotency-Key'] = `${__ENV.RUN_ID}-${brand}-${iteration}`;
    http.post(`${__ENV.ORDER_URL}/orders`, JSON.stringify({ menuId: 'menu-1', quantity: 1 }), {
      headers, timeout: '5s', redirects: 0, tags: { operation: 'order', name: 'POST /orders' },
    });
  } else {
    http.get(`${__ENV.CATALOG_URL}/catalog`, {
      headers, timeout: '5s', redirects: 0, tags: { operation: 'catalog', name: 'GET /catalog' },
    });
  }
}
