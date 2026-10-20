import assert from "node:assert/strict";
import test from "node:test";
import {ClubClient} from "../publish/client.js";

test("client sends UID authorization and stable action envelope", async () => {
  const requests = [];
  const client = new ClubClient({
    sdk: {user: {info: async () => ({id: "employee-1"})}},
    apiBase: "https://club.test",
    fetchImpl: async (url, options) => {
      requests.push({url, options});
      return {ok: true, json: async () => ({version: 2})};
    },
  });
  await client.action("room-1", 1, "ready");
  const body = JSON.parse(requests[0].options.body);
  assert.equal(requests[0].options.headers.Authorization, "ClubUid employee-1");
  assert.equal(body.version, 1);
  assert.equal(body.action, "ready");
  assert.match(body.request_id, /^[0-9a-f-]+$/);
});
