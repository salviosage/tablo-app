import { useState, useEffect } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function App() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios
      .get(`${API_BASE}/api/status`)
      .then((r) => setStatus(r.data))
      .catch(() => setError("Cannot reach API"));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-gradient-to-r from-emerald-900 to-teal-800 text-white px-8 py-6">
        <p className="text-xs tracking-widest uppercase opacity-60 mb-1">
          tablo
        </p>
        <h1 className="text-2xl font-bold tracking-tight">
          Your documents talk to each other
        </h1>
      </header>

      <main className="max-w-4xl mx-auto px-8 py-12">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg px-6 py-4 mb-8">
            {error} — is the backend running?
          </div>
        )}

        {status && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              System status
            </h2>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(status.features).map(([feature, enabled]) => (
                <div
                  key={feature}
                  className="flex items-center gap-3 px-4 py-3 rounded-lg bg-gray-50"
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      enabled ? "bg-emerald-500" : "bg-gray-300"
                    }`}
                  />
                  <span className="text-sm text-gray-700 capitalize">
                    {feature}
                  </span>
                  <span className="ml-auto text-xs text-gray-400">
                    {enabled ? "ready" : "pending"}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-6 text-sm text-gray-500">
              API connected — v{status.status === "running" ? "0.1.0" : "?"}
            </p>
          </div>
        )}

        {!status && !error && (
          <div className="text-center text-gray-400 py-20">
            Connecting to API...
          </div>
        )}
      </main>
    </div>
  );
}
