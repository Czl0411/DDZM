function buildRandomEventSubmissionsPath(page, pageSize, status) {
  const params = new URLSearchParams({page: String(page), page_size: String(pageSize)});
  if (status) params.set("status", status);
  return `/api/game/random-events/submissions?${params.toString()}`;
}

if (typeof module !== "undefined") {
  module.exports = {buildRandomEventSubmissionsPath};
}
