"use client";

import Link from "next/link";

const STEPS = [
  {
    number: "01",
    icon: "📁",
    title: "Utwórz projekt",
    color: "text-blue-400",
    border: "border-blue-500/20",
    bg: "bg-blue-500/5",
    content: (
      <>
        <p className="text-xs text-buddy-text-muted leading-relaxed">
          Kliknij <span className="font-semibold text-buddy-text">„+ Nowy projekt"</span> w panelu
          bocznym i nadaj projektowi nazwę — np. nazwę systemu lub modułu, który testujesz.
        </p>
        <p className="mt-2 text-xs text-buddy-text-muted leading-relaxed">
          Każdy projekt ma osobną bazę wiedzy, rejestr wymagań i historię audytów.
        </p>
      </>
    ),
  },
  {
    number: "02",
    icon: "🧠",
    title: "Zbuduj kontekst (M1 Context Builder)",
    color: "text-purple-400",
    border: "border-purple-500/20",
    bg: "bg-purple-500/5",
    content: (
      <>
        <p className="text-xs text-buddy-text-muted leading-relaxed">
          Wgraj dokumentację projektu: SRS, plan testów, eksporty z Confluence, dokumenty
          architektury — formaty <span className="font-mono text-buddy-text">.docx</span> i{" "}
          <span className="font-mono text-buddy-text">.pdf</span>.
        </p>
        <p className="mt-2 text-xs text-buddy-text-muted leading-relaxed">
          System buduje bazę wiedzy (RAG), mapę myśli i słownik pojęć domenowych.{" "}
          <span className="text-buddy-text">Im więcej dokumentów, tym lepsza analiza.</span>
        </p>
        <div className="mt-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-buddy-border/40 border border-buddy-border">
          <span className="text-buddy-gold text-xs shrink-0 mt-0.5">💡</span>
          <p className="text-[11px] text-buddy-text-muted leading-relaxed">
            Nie masz pliku .docx? Wyeksportuj strony z Confluence do PDF — system obsłuży oba formaty.
          </p>
        </div>
      </>
    ),
  },
  {
    number: "03",
    icon: "📋",
    title: "Wyodrębnij wymagania (Faza 2)",
    color: "text-amber-400",
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    content: (
      <>
        <p className="text-xs text-buddy-text-muted leading-relaxed">
          Przejdź do{" "}
          <span className="font-semibold text-buddy-text">„📋 Requirements"</span> w panelu bocznym
          i kliknij <span className="font-semibold text-buddy-text">„Wyodrębnij wymagania"</span>.
        </p>
        <p className="mt-2 text-xs text-buddy-text-muted leading-relaxed">
          System analizuje dokumentację i wyodrębnia wymagania z oceną wiarygodności (confidence
          score). Elementy z{" "}
          <span className="text-amber-400 font-medium">bursztynową ramką</span> wymagają Twojej
          weryfikacji — kliknij, by potwierdzić lub edytować.
        </p>
        <p className="mt-2 text-xs text-buddy-text-muted leading-relaxed">
          Ten krok tworzy <span className="text-buddy-text font-medium">punkt bazowy do analizy pokrycia</span>.
        </p>
      </>
    ),
  },
  {
    number: "04",
    icon: "📁",
    title: "Wgraj test case'y",
    color: "text-emerald-400",
    border: "border-emerald-500/20",
    bg: "bg-emerald-500/5",
    content: (
      <>
        <p className="text-xs text-buddy-text-muted leading-relaxed">
          Przejdź do <span className="font-semibold text-buddy-text">„🔍 Suite Analyzer"</span> i
          wgraj swój zestaw testów. Obsługiwane formaty:{" "}
          <span className="font-mono text-buddy-text">.xlsx</span>,{" "}
          <span className="font-mono text-buddy-text">.csv</span>,{" "}
          <span className="font-mono text-buddy-text">.feature</span>,{" "}
          <span className="font-mono text-buddy-text">.json</span>.
        </p>
        <p className="mt-2 text-xs text-buddy-text-muted leading-relaxed">
          Możesz wgrać eksporty z Zephyr/Xray, ręczne arkusze z test case&apos;ami lub kod
          automatyzacji.
        </p>
      </>
    ),
  },
  {
    number: "05",
    icon: "🗺️",
    title: "Uruchom analizę pokrycia (Faza 5+6)",
    color: "text-sky-400",
    border: "border-sky-500/20",
    bg: "bg-sky-500/5",
    content: (
      <>
        <p className="text-xs text-buddy-text-muted leading-relaxed">
          Na stronie Requirements kliknij{" "}
          <span className="font-semibold text-buddy-text">„Uruchom mapping"</span>. System
          semantycznie dopasowuje każde wymaganie do test case&apos;ów i oblicza wynik pokrycia 0–100%.
        </p>
        <div className="mt-3 grid grid-cols-4 gap-2">
          {[
            { icon: "🟢", label: "≥ 80%", note: "dobre pokrycie" },
            { icon: "🟡", label: "60–79%", note: "do poprawy" },
            { icon: "🟠", label: "30–59%", note: "słabe" },
            { icon: "🔴", label: "< 30%", note: "krytyczna luka" },
          ].map(({ icon, label, note }) => (
            <div
              key={label}
              className="flex flex-col items-center gap-1 px-2 py-2 rounded-lg bg-buddy-border/30 border border-buddy-border"
            >
              <span className="text-base leading-none">{icon}</span>
              <span className="text-[10px] font-mono text-buddy-text font-semibold">{label}</span>
              <span className="text-[9px] text-buddy-text-faint text-center leading-tight">{note}</span>
            </div>
          ))}
        </div>
      </>
    ),
  },
  {
    number: "06",
    icon: "🔍",
    title: "Audyt test suite (M2 Suite Analyzer)",
    color: "text-rose-400",
    border: "border-rose-500/20",
    bg: "bg-rose-500/5",
    content: (
      <>
        <p className="text-xs text-buddy-text-muted leading-relaxed">
          Przejdź do{" "}
          <span className="font-semibold text-buddy-text">„🔍 Suite Analyzer"</span> i uruchom
          audyt. System wykorzystuje rejestr wymagań i wyniki pokrycia, by wygenerować konkretne
          rekomendacje:
        </p>
        <ul className="mt-2 space-y-1">
          {[
            "Co jest nieprzetestowane (brakujące wymagania)",
            "Co jest zduplikowane (redundantne test case'y)",
            "Co wymaga uwagi (niskie pokrycie krytycznych obszarów)",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2 text-xs text-buddy-text-muted">
              <span className="text-buddy-gold shrink-0 mt-0.5">→</span>
              {item}
            </li>
          ))}
        </ul>
      </>
    ),
  },
];

const TIPS = [
  "Wgraj jak najwięcej dokumentów — więcej kontekstu = lepsza analiza",
  "Weryfikuj wymagania z bursztynową flagą — Twoja wiedza ekspercka ulepsza system",
  "Uruchom mapping ponownie po dodaniu nowych test case'ów",
  "Użyj czatu RAG na stronie Context Builder, by zadawać pytania o domenę",
];

export default function GettingStartedPage() {
  return (
    <div className="min-h-screen bg-buddy-base text-buddy-text font-sans">
      <div className="max-w-2xl mx-auto px-6 py-12">

        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-buddy-gold to-buddy-gold-light flex items-center justify-center text-base font-bold text-buddy-surface shrink-0">
              Q
            </div>
            <span className="text-[13px] font-semibold text-buddy-gold-light tracking-tight">
              AI Buddy
            </span>
          </div>
          <h1 className="text-2xl font-semibold text-buddy-text tracking-tight">
            Jak korzystać z AI Buddy
          </h1>
          <p className="mt-2 text-sm text-buddy-text-muted leading-relaxed">
            Przewodnik dla inżyniera QA — od pustego projektu do pełnej analizy pokrycia
            wymagań w 6 krokach.
          </p>
        </div>

        {/* Steps */}
        <div className="flex flex-col gap-4">
          {STEPS.map((step, i) => (
            <div
              key={step.number}
              className={`rounded-xl border ${step.border} ${step.bg} p-5`}
            >
              <div className="flex items-start gap-3">
                <div className="shrink-0 flex flex-col items-center gap-1">
                  <span className="text-xl leading-none">{step.icon}</span>
                  <span className={`text-[10px] font-mono font-semibold ${step.color}`}>
                    {step.number}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-sm font-semibold text-buddy-text mb-2">
                    {step.title}
                  </h2>
                  {step.content}
                </div>
              </div>
              {/* Connector arrow */}
              {i < STEPS.length - 1 && (
                <div className="mt-4 flex justify-center">
                  <span className="text-buddy-text-faint text-xs">↓</span>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Tips */}
        <div className="mt-8 rounded-xl border border-buddy-gold/20 bg-buddy-gold/5 p-5">
          <h2 className="text-sm font-semibold text-buddy-gold-light mb-3">💡 Porady</h2>
          <ul className="space-y-2">
            {TIPS.map((tip) => (
              <li key={tip} className="flex items-start gap-2 text-xs text-buddy-text-muted leading-relaxed">
                <span className="text-buddy-gold shrink-0 mt-0.5">·</span>
                {tip}
              </li>
            ))}
          </ul>
        </div>

        {/* CTA */}
        <div className="mt-8 flex justify-center">
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-buddy-gold to-buddy-gold-light text-buddy-surface text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity"
          >
            Rozpocznij →
          </Link>
        </div>

        {/* Footer */}
        <p className="mt-8 text-center text-[11px] text-buddy-text-faint">
          AI Buddy — QA Agent Platform
        </p>
      </div>
    </div>
  );
}
