import axios from "axios";

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
});

export async function checkStatus() {
  const { data } = await API.get("/api/status");
  return data;
}

export async function uploadFiles(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const { data } = await API.post("/api/upload", form);
  return data;
}

export async function processJob(jobId) {
  const { data } = await API.post(`/api/jobs/${jobId}/process`);
  return data;
}

export async function getJob(jobId) {
  const { data } = await API.get(`/api/jobs/${jobId}`);
  return data;
}
