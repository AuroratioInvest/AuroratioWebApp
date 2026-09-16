import client from "./client";

export async function runExecutionNow(userId?: string) {
  const res = await client.post("/execution/run-now", null, {
    params: userId ? { user_id: userId } : undefined,
  });

  return res.data;
}

export async function runMyExecution() {
  const res = await client.post("/execution/run-me");
  return res.data;
}

export async function getExecutionMode() {
  const res = await client.get("/execution/mode");
  return res.data;
}

export async function getExecutionLogs(userId?: string) {
  const res = await client.get("/execution/logs", {
    params: userId ? { user_id: userId } : undefined,
  });

  return res.data;
}

export async function getMyExecutionLogs() {
  const res = await client.get("/execution/my-logs");
  return res.data;
}

export async function getExecutionState() {
  const res = await client.get("/execution/state");
  return res.data;
}

export async function resetModule(moduleName: string) {
  const res = await client.post(`/execution/modules/${moduleName}/reset`);
  return res.data;
}

export async function pauseModule(moduleName: string) {
  const res = await client.post(`/execution/modules/${moduleName}/pause`);
  return res.data;
}

export async function resumeModule(moduleName: string) {
  const res = await client.post(`/execution/modules/${moduleName}/resume`);
  return res.data;
}

export async function getLatestBotReport() {
  const res = await client.get("/execution/reports/latest");
  return res.data;
}

export async function getBotReports() {
  const res = await client.get("/execution/reports");
  return res.data;
}