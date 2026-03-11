"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function Home() {
  const router = useRouter();
  const [projectId, setProjectId] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = projectId.trim();
    if (id) router.push(`/chat/${encodeURIComponent(id)}`);
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-buddy-base p-8">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-buddy-gold to-buddy-gold-light text-xl font-bold text-buddy-surface mb-2">
            Q
          </div>
          <h1 className="text-3xl font-semibold text-buddy-gold-light">AI Buddy</h1>
          <p className="text-buddy-text-muted text-sm">
            QA Agent Platform — Test Suite Audit &amp; Optimization
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-buddy-surface border border-buddy-border rounded-xl p-6 space-y-4"
        >
          <div className="space-y-1.5">
            <label
              className="text-sm font-medium text-buddy-text-muted"
              htmlFor="project-id"
            >
              Project ID
            </label>
            <input
              id="project-id"
              type="text"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="e.g. my-project"
              className="w-full rounded-lg border border-buddy-border-dark bg-buddy-elevated px-3 py-2 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold"
            />
          </div>
          <button
            type="submit"
            disabled={!projectId.trim()}
            className="w-full rounded-lg bg-gradient-to-r from-buddy-gold to-buddy-gold-light px-4 py-2 text-sm font-semibold text-buddy-surface hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            Open Chat
          </button>
        </form>
      </div>
    </main>
  );
}
