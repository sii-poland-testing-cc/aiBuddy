"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      if (res.status === 401) {
        setError("Nieprawidłowy e-mail lub hasło.");
      } else if (res.status === 422) {
        setError("Sprawdź poprawność danych i spróbuj ponownie.");
      } else if (!res.ok) {
        setError("Błąd serwera. Spróbuj ponownie za chwilę.");
      } else {
        router.push("/");
      }
    } catch {
      setError("Błąd serwera. Spróbuj ponownie za chwilę.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-buddy-base p-8">
      <div className="w-full max-w-[420px] px-2">
        {/* Logo mark */}
        <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-buddy-gold to-buddy-gold-light mb-6" />

        <h1 className="text-xl font-semibold text-buddy-text">Zaloguj się</h1>
        <p className="text-sm text-buddy-text-muted mt-1 mb-8">
          Wpisz swoje dane, aby kontynuować
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          <div>
            <label htmlFor="email" className="block text-sm font-semibold text-buddy-text mb-2">
              Adres e-mail
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full bg-buddy-elevated border border-buddy-border rounded-xl px-4 py-3 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold transition-colors duration-150"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-semibold text-buddy-text mb-2">
              Hasło
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full bg-buddy-elevated border border-buddy-border rounded-xl px-4 py-3 text-sm text-buddy-text placeholder:text-buddy-text-faint focus:outline-none focus:border-buddy-gold transition-colors duration-150"
            />
          </div>

          {error && (
            <div role="alert" className="mt-2 px-3 py-2 rounded-lg bg-buddy-error/10 border border-buddy-error/30 text-sm text-buddy-error">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-3 min-h-[44px] bg-buddy-gold rounded-xl text-sm font-medium text-buddy-surface hover:bg-buddy-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
          >
            {loading ? "Ładowanie…" : "Zaloguj się"}
          </button>
        </form>

        <p className="text-sm text-buddy-text-muted mt-6 text-center">
          Nie masz konta?{" "}
          <Link href="/register" className="cursor-pointer text-buddy-gold hover:text-buddy-gold-light underline-offset-2 hover:underline">
            Zarejestruj się
          </Link>
        </p>
      </div>
    </div>
  );
}
