from __future__ import annotations

from datetime import datetime, timezone
from string import Template

from als_intel.brand import (
    DEFAULT_GITHUB_URL,
    LANDING_DASHBOARD_URL_PATH,
    LETTERMARK_LOGO_URL_PATH,
    favicon_link_tag,
)

APP_ROUTE = "/app"

LANDING_TEMPLATE = Template(
    """
<!DOCTYPE html>
<html class="scroll-smooth" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>MTVL AI | ALS Scientific Intelligence</title>
$favicon_tag
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    "colors": {
                        "surface-container-low": "#f3f3fb",
                        "outline": "#747783",
                        "on-secondary": "#ffffff",
                        "surface-container-lowest": "#ffffff",
                        "secondary-container": "#6292fd",
                        "surface-bright": "#faf8ff",
                        "primary-fixed": "#d9e2ff",
                        "on-background": "#1a1b21",
                        "surface-variant": "#e2e2e9",
                        "surface-container-highest": "#e2e2e9",
                        "primary": "#002764",
                        "surface": "#faf8ff",
                        "on-primary-container": "#88abff",
                        "background": "#faf8ff",
                        "surface-container": "#eeedf5",
                        "on-primary": "#ffffff",
                        "primary-container": "#003c90",
                        "outline-variant": "#c3c6d3",
                        "on-surface": "#1a1b21",
                        "on-surface-variant": "#434652",
                        "secondary": "#1d59c1",
                        "surface-container-high": "#e8e7ef",
                        "primary-fixed-dim": "#b0c6ff",
                        "error": "#ba1a1a",
                        "on-tertiary-container": "#ff8e63"
                    },
                    "borderRadius": {
                        "DEFAULT": "0.125rem",
                        "lg": "0.25rem",
                        "xl": "0.5rem",
                        "full": "0.75rem"
                    },
                    "spacing": {
                        "margin-desktop": "32px",
                        "stack-lg": "32px",
                        "stack-md": "16px",
                        "container-max": "1280px",
                        "margin-mobile": "16px",
                        "gutter": "24px",
                        "header-height": "64px",
                        "stack-sm": "8px"
                    },
                    "fontFamily": {
                        "title-md": ["Inter"],
                        "code-label": ["JetBrains Mono"],
                        "body-sm": ["Inter"],
                        "headline-lg": ["Inter"],
                        "display-lg": ["Inter"],
                        "body-base": ["Inter"]
                    },
                    "fontSize": {
                        "title-md": ["20px", {"lineHeight": "28px", "fontWeight": "600"}],
                        "code-label": ["13px", {"lineHeight": "16px", "fontWeight": "500"}],
                        "body-sm": ["14px", {"lineHeight": "22px", "fontWeight": "400"}],
                        "headline-lg": ["32px", {"lineHeight": "40px", "fontWeight": "600"}],
                        "display-lg": ["48px", {"lineHeight": "56px", "fontWeight": "600"}],
                        "body-base": ["16px", {"lineHeight": "26px", "fontWeight": "400"}]
                    }
                },
            },
        }
    </script>
<style>
        .glass-header {
            background: rgba(250, 248, 255, 0.9);
            backdrop-filter: blur(12px);
        }
        .bento-card {
            transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.2s ease;
        }
        .bento-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }
        .landing-db-widget {
            background: linear-gradient(145deg, #ffffff 0%, #f3f3fb 100%);
            border: 1px solid rgba(116, 119, 131, 0.22);
            box-shadow: 0 18px 40px -24px rgba(0, 39, 100, 0.35);
        }
        .landing-db-widget.loading .landing-db-skeleton {
            position: relative;
            overflow: hidden;
            background: #e8e7ef;
            border-radius: 999px;
        }
        .landing-db-widget.loading .landing-db-skeleton::after {
            content: '';
            position: absolute;
            inset: 0;
            transform: translateX(-100%);
            background: linear-gradient(90deg, rgba(226, 232, 240, 0) 0%, rgba(248, 250, 252, 0.9) 50%, rgba(226, 232, 240, 0) 100%);
            animation: landing-shimmer 1.2s ease-in-out infinite;
        }
        @keyframes landing-shimmer {
            100% { transform: translateX(100%); }
        }
    </style>
</head>
<body class="bg-surface text-on-surface font-body-base antialiased">
<header class="fixed top-0 w-full z-50 glass-header border-b border-outline-variant/30 shadow-sm">
<nav class="flex justify-between items-center h-header-height px-margin-desktop max-w-container-max mx-auto">
<div class="flex items-center gap-stack-sm">
<a href="/" class="flex items-center gap-stack-sm">
<img alt="MTVL AI" class="h-8 w-auto" src="$logo_url"/>
<span class="font-title-md text-title-md font-bold text-primary tracking-tight">MTVL AI</span>
</a>
</div>
<div class="hidden md:flex items-center gap-8">
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#database">Database</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#features">Features</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#how-it-works">How it works</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#governance">Governance</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#open-source">Community</a>
</div>
<div class="flex items-center gap-stack-md">
<a class="hidden sm:block text-on-surface-variant hover:text-primary font-body-sm text-body-sm transition-colors" href="/docs/MISSION.md">Documentation</a>
<a class="bg-primary-container text-white px-5 py-2 rounded font-body-sm text-body-sm hover:opacity-90 transition-all active:scale-95 shadow-sm" href="$primary_cta_href">$primary_cta_label</a>
</div>
</nav>
</header>
<main class="pt-24 overflow-x-hidden">
<section class="max-w-container-max mx-auto px-margin-desktop py-stack-lg lg:py-24 grid grid-cols-1 lg:grid-cols-2 gap-gutter items-center">
<div class="space-y-stack-md">
<div class="inline-flex items-center px-3 py-1 bg-primary/5 text-primary-container border border-primary/10 rounded-full font-code-label text-code-label">
                    LOCAL-FIRST · OPEN SOURCE · EVIDENCE-GROUNDED
                </div>
<h1 class="font-display-lg text-display-lg text-primary tracking-tight leading-tight">
                    Reduce ALS research uncertainty with traceable, cited intelligence
                </h1>
<p class="text-on-surface-variant font-body-base text-body-base max-w-xl">
                    MTVL AI connects 15 public biomedical sources into a single investigator workspace. Ask questions, compare contradictions, and promote hypotheses—with every claim tied back to source evidence.
                </p>
<div class="flex flex-wrap gap-stack-md pt-stack-sm">
<a class="bg-primary-container text-white px-8 py-3 rounded-lg font-title-md text-title-md flex items-center gap-2 hover:bg-primary transition-all" href="$primary_cta_href">
                        $hero_cta_label
                        <span class="material-symbols-outlined">arrow_forward</span>
</a>
<a class="border border-outline-variant text-primary px-8 py-3 rounded-lg font-title-md text-title-md hover:bg-surface-container-low transition-all" href="$github_url" target="_blank" rel="noopener noreferrer">
                        View on GitHub
                    </a>
</div>
<div class="flex items-center gap-2 text-outline font-body-sm text-body-sm pt-4">
<span class="material-symbols-outlined text-[18px]">verified_user</span>
                    Magic-link sign-in · Local SQLite storage · Human review gates
                </div>
</div>
<div class="relative group">
<div class="absolute -inset-4 bg-gradient-to-tr from-primary/5 to-secondary/10 blur-3xl opacity-50 rounded-full"></div>
<div class="relative rounded-xl border border-outline-variant overflow-hidden shadow-2xl">
<img alt="MTVL AI Dashboard Mockup" class="w-full h-auto object-cover group-hover:scale-105 transition-transform duration-700" src="$dashboard_image_url"/>
</div>
</div>
</section>
<section class="bg-surface-container-low border-y border-outline-variant/30 py-12">
<div class="max-w-container-max mx-auto px-margin-desktop grid grid-cols-2 lg:grid-cols-4 gap-gutter text-center">
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">15</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">Public data sources</div>
</div>
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">30k+</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">Evidence records</div>
</div>
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">55</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">Fidelity gold cases</div>
</div>
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">100%</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">CI-gated quality</div>
</div>
</div>
<p class="text-center text-on-surface-variant font-body-sm text-body-sm mt-6 px-margin-desktop">Self-hosted deployment counts vary.</p>
</section>
<section class="max-w-container-max mx-auto px-margin-desktop py-24" id="database">
<div class="grid grid-cols-1 lg:grid-cols-2 gap-gutter items-center">
<div class="space-y-stack-md">
<div class="inline-flex items-center px-3 py-1 bg-primary/5 text-primary-container border border-primary/10 rounded-full font-code-label text-code-label">
                    LIVE LOCAL EVIDENCE STORE
                </div>
<h2 class="font-headline-lg text-headline-lg text-primary">Your database, ready to investigate</h2>
<p class="text-on-surface-variant font-body-base text-body-base max-w-xl">
                    MTVL AI keeps a local SQLite evidence store synced from public biomedical APIs. Inspect source coverage, freshness, and volume before you sign in—then query with grounded citations in the investigator workspace.
                </p>
<a class="inline-flex items-center gap-2 bg-primary-container text-white px-8 py-3 rounded-lg font-title-md text-title-md hover:bg-primary transition-all shadow-md active:scale-95" href="$primary_cta_href">
                    $database_cta_label
                    <span class="material-symbols-outlined">database</span>
                </a>
</div>
<div id="landingDbWidget" class="landing-db-widget rounded-xl p-stack-lg loading">
<div class="flex justify-between items-center mb-4">
<h3 class="font-title-md text-title-md text-primary">Database status</h3>
<div class="flex items-center gap-2">
<span id="landingDbDot" class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
<span id="landingDbUpdated" class="text-on-surface-variant font-body-sm text-body-sm">Checking...</span>
</div>
</div>
<div class="flex items-baseline gap-2 mb-4">
<span id="landingDbTotal" class="font-display-lg text-headline-lg text-primary">-</span>
<span class="text-on-surface-variant font-body-sm text-body-sm">evidence nodes</span>
</div>
<div id="landingDbSources" class="space-y-3 mb-4">
<div class="landing-db-skeleton h-2.5 w-full"></div>
<div class="landing-db-skeleton h-2.5 w-[86%]"></div>
<div class="landing-db-skeleton h-2.5 w-[73%]"></div>
</div>
<p id="landingDbState" class="text-on-surface-variant font-body-sm text-body-sm border-t border-outline-variant/30 pt-4">Loading database state...</p>
</div>
</div>
</section>
<section class="max-w-container-max mx-auto px-margin-desktop py-24">
<h2 class="font-headline-lg text-headline-lg text-center mb-16 text-primary">Engineered for scientific rigor</h2>
<div class="grid grid-cols-1 md:grid-cols-3 gap-gutter">
<div class="bento-card p-stack-lg bg-white border border-outline-variant rounded-xl border-l-4 border-l-secondary">
<div class="w-12 h-12 bg-primary/5 rounded-lg flex items-center justify-center text-primary mb-6">
<span class="material-symbols-outlined text-3xl">description</span>
</div>
<h3 class="font-title-md text-title-md mb-3 text-primary">Evidence you can audit</h3>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">Every synthesis cites claim IDs and source metadata. Reliability scores and extraction provenance stay inspectable—not buried in model weights.</p>
</div>
<div class="bento-card p-stack-lg bg-white border border-outline-variant rounded-xl border-l-4 border-l-secondary">
<div class="w-12 h-12 bg-primary/5 rounded-lg flex items-center justify-center text-primary mb-6">
<span class="material-symbols-outlined text-3xl">compare</span>
</div>
<h3 class="font-title-md text-title-md mb-3 text-primary">Contradictions stay visible</h3>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">Supporting and contradicting studies surface together. Failure atlases and debate protocols help you see why trials fail—not just what succeeded in abstracts.</p>
</div>
<div class="bento-card p-stack-lg bg-white border border-outline-variant rounded-xl border-l-4 border-l-secondary">
<div class="w-12 h-12 bg-primary/5 rounded-lg flex items-center justify-center text-primary mb-6">
<span class="material-symbols-outlined text-3xl">storage</span>
</div>
<h3 class="font-title-md text-title-md mb-3 text-primary">Local-first control</h3>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">Run on your infrastructure with SQLite, optional Docker, and your own Ollama models. No mandatory cloud exfiltration for core workflows.</p>
</div>
</div>
</section>
<section class="bg-surface-container-lowest py-24" id="features">
<div class="max-w-container-max mx-auto px-margin-desktop">
<div class="max-w-2xl mb-16">
<h2 class="font-headline-lg text-headline-lg text-primary mb-4">A complete ecosystem for neurodegenerative data</h2>
<p class="text-on-surface-variant">Sophisticated tools built specifically for the high-dimensional challenges of ALS research.</p>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">Incremental sync</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">Pull ALS-related records from PubMed, ClinicalTrials.gov, PMC, ChEMBL, GEO, and 10 more public sources on a schedule.</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">Structured extraction</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">Normalize entities, relations, outcomes, and effect directions across all 15 public sources with inspectable provenance.</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">Grounded chat</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">Ask investigation questions; answers cite in-database evidence via a local LLM (Ollama) with guardrails.</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">Hypothesis queue</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">Rank testable directions with supporting and contradictory evidence cards and reviewer sign-off gates.</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">Failure atlas</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">Map terminated trials and negative endpoints to root-cause patterns for investigator review.</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">Automation &amp; gates</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">Nightly ops, benchmark gates, and extraction fidelity checks before hypotheses are promoted.</p>
</div>
</div>
</div>
</section>
<section class="py-24 max-w-container-max mx-auto px-margin-desktop" id="how-it-works">
<h2 class="font-headline-lg text-headline-lg text-center mb-16 text-primary">The Investigation Pipeline</h2>
<div class="relative grid grid-cols-1 md:grid-cols-4 gap-gutter">
<div class="hidden md:block absolute top-12 left-0 w-full h-[2px] bg-outline-variant/30 z-0"></div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">1</div>
<h5 class="font-title-md text-title-md text-primary mb-2">Ingest</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">Scheduled sync from public biomedical APIs into your local evidence store.</p>
</div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">2</div>
<h5 class="font-title-md text-title-md text-primary mb-2">Structure</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">Extract entities, relations, outcomes, and trial provenance from raw documents.</p>
</div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">3</div>
<h5 class="font-title-md text-title-md text-primary mb-2">Investigate</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">Query, compare nodes, and generate synthesis reports with citations.</p>
</div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">4</div>
<h5 class="font-title-md text-title-md text-primary mb-2">Validate</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">Human reviewers approve, reject, or withhold promotion through explicit gates.</p>
</div>
</div>
<div class="mt-16 text-center">
<a class="inline-flex items-center gap-2 bg-primary-container text-white px-10 py-4 rounded-lg font-title-md text-title-md hover:bg-primary transition-all shadow-lg active:scale-95" href="$primary_cta_href">
                    $pipeline_cta_label
                    <span class="material-symbols-outlined">launch</span>
</a>
</div>
</section>
<section class="max-w-container-max mx-auto px-margin-desktop mb-24" id="governance">
<div class="bg-surface-container-high rounded-xl overflow-hidden flex flex-col md:flex-row shadow-sm border border-outline-variant/30">
<div class="w-2 bg-primary"></div>
<div class="p-stack-lg flex-1">
<h3 class="font-title-md text-title-md text-primary mb-4 flex items-center gap-2">
<span class="material-symbols-outlined text-secondary">gavel</span>
                        Research Governance &amp; Ethics
                    </h3>
<div class="grid grid-cols-1 md:grid-cols-2 gap-gutter">
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">
                            Canoniga is designed for scientific discovery support—not clinical decision-making. Outputs may be incomplete or affected by publication bias; all conclusions require experimental validation and qualified human oversight.
                        </p>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">
                            The platform preserves contradictory findings, flags high-risk causal claims, and requires human sign-off for high-impact promotion paths. Governance docs are available offline at <a href="/docs/MISSION.md" class="text-primary hover:underline">/docs</a>.
                        </p>
</div>
</div>
</div>
</section>
<section class="py-24 bg-primary text-white overflow-hidden" id="open-source">
<div class="max-w-container-max mx-auto px-margin-desktop grid grid-cols-1 lg:grid-cols-2 gap-24 items-center">
<div>
<h2 class="font-display-lg text-headline-lg mb-6">Deploy on your terms</h2>
<p class="text-primary-fixed font-body-base text-body-base mb-8">
                        Docker-ready stack with Mailpit for dev auth, production SMTP checklist, and documented nightly-ops runbook. Fork, audit, and extend the pipeline.
                    </p>
<div class="space-y-4">
<div class="flex items-center gap-4">
<div class="w-10 h-10 rounded bg-white/10 flex items-center justify-center">
<span class="material-symbols-outlined">terminal</span>
</div>
<span class="font-code-label text-code-label">make web-up</span>
</div>
<div class="flex items-center gap-4">
<div class="w-10 h-10 rounded bg-white/10 flex items-center justify-center">
<span class="material-symbols-outlined">hub</span>
</div>
<span class="font-code-label text-code-label">make nightly-ops</span>
</div>
<div class="flex items-center gap-4">
<div class="w-10 h-10 rounded bg-white/10 flex items-center justify-center">
<span class="material-symbols-outlined">check_circle</span>
</div>
<span class="font-code-label text-code-label">make test-extraction-fidelity</span>
</div>
</div>
<a class="inline-block mt-8 border border-white/40 text-white px-8 py-3 rounded-lg font-title-md hover:bg-white/10 transition-all" href="$github_url" target="_blank" rel="noopener noreferrer">Explore the repository</a>
</div>
<div class="relative">
<div class="bg-surface-container-highest/10 backdrop-blur-md rounded-xl border border-white/20 p-6 font-code-label text-code-label text-primary-fixed shadow-2xl">
<div class="flex gap-2 mb-4">
<div class="w-3 h-3 rounded-full bg-error"></div>
<div class="w-3 h-3 rounded-full bg-secondary-container"></div>
<div class="w-3 h-3 rounded-full bg-on-primary-container"></div>
</div>
<div class="space-y-1 opacity-80">
<p><span class="text-on-tertiary-container"># Nightly operations</span></p>
<p>export ALS_AUTOMATION_WORKER_TOKEN="..."</p>
<p>make nightly-ops</p>
<p class="mt-4"><span class="text-secondary-container"># Extraction fidelity gate</span></p>
<p>make test-extraction-fidelity</p>
</div>
</div>
</div>
</div>
</section>
</main>
<footer class="bg-surface-container-high border-t border-outline-variant w-full py-stack-lg">
<div class="grid grid-cols-1 md:grid-cols-2 gap-gutter px-margin-desktop max-w-container-max mx-auto">
<div class="space-y-stack-md">
<div class="flex items-center gap-2">
<span class="font-title-md text-title-md font-bold text-primary tracking-tight">MTVL AI</span>
</div>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed pr-8">
                    © $current_year MTVL AI. Open-source ALS intelligence. Not medical advice. Not for patient diagnosis or treatment decisions. Research assistance only.
                </p>
</div>
<div class="grid grid-cols-2 gap-gutter">
<div class="space-y-3">
<h6 class="font-title-md text-[14px] uppercase tracking-widest text-primary">Resources</h6>
<ul class="space-y-2">
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/docs/MISSION.md">Documentation</a></li>
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="$github_url" target="_blank" rel="noopener noreferrer">GitHub</a></li>
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/docs/ETHICS_AND_OVERSIGHT.md">Research Ethics</a></li>
</ul>
</div>
<div class="space-y-3">
<h6 class="font-title-md text-[14px] uppercase tracking-widest text-primary">Legal</h6>
<ul class="space-y-2">
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/privacy">Privacy Policy</a></li>
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/terms">Terms of Service</a></li>
</ul>
</div>
</div>
</div>
</footer>
<script>
        function landingFormatCount(value) {
            const count = Number(value || 0);
            if (!Number.isFinite(count) || count < 0) return '0';
            return count.toLocaleString();
        }
        function landingFormatRelative(isoText) {
            if (!isoText) return 'n/a';
            const parsed = new Date(String(isoText));
            if (Number.isNaN(parsed.getTime())) return String(isoText);
            const minutes = Math.round((Date.now() - parsed.getTime()) / 60000);
            if (minutes < 1) return 'just now';
            if (minutes < 60) return minutes + 'm ago';
            const hours = Math.round(minutes / 60);
            if (hours < 48) return hours + 'h ago';
            return Math.round(hours / 24) + 'd ago';
        }
        function landingRenderSources(rows, total) {
            const root = document.getElementById('landingDbSources');
            if (!root) return;
            const safeRows = Array.isArray(rows) ? rows : [];
            if (!safeRows.length) {
                root.innerHTML = '<p class="text-on-surface-variant font-body-sm text-body-sm">No source metadata available yet.</p>';
                return;
            }
            const denom = total > 0 ? total : 1;
            const shades = ['bg-primary-container', 'bg-secondary', 'bg-primary', 'bg-blue-700', 'bg-slate-500'];
            root.innerHTML = safeRows.slice(0, 5).map((row, index) => {
                const source = String(row && row.source ? row.source : 'unknown');
                const count = Number(row && row.articles ? row.articles : 0);
                const safeCount = Number.isFinite(count) && count > 0 ? count : 0;
                const width = Math.max(0, Math.min(100, (safeCount / denom) * 100));
                const cls = shades[Math.min(index, shades.length - 1)];
                return '<div class="space-y-1">'
                    + '<div class="flex justify-between text-on-surface-variant font-body-sm text-body-sm"><span>' + source + '</span><span>' + landingFormatCount(safeCount) + '</span></div>'
                    + '<div class="w-full h-1.5 bg-surface-container rounded-full overflow-hidden"><div class="' + cls + ' h-full rounded-full" style="width:' + width.toFixed(1) + '%"></div></div>'
                    + '</div>';
            }).join('');
        }
        async function landingFetchDbStatus() {
            const widget = document.getElementById('landingDbWidget');
            const totalEl = document.getElementById('landingDbTotal');
            const updatedEl = document.getElementById('landingDbUpdated');
            const stateEl = document.getElementById('landingDbState');
            const dotEl = document.getElementById('landingDbDot');
            if (widget) widget.classList.add('loading');
            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'status failed');
                const total = Number(data.records_total || 0);
                const syncText = landingFormatRelative(data.latest_sync_at);
                if (widget) widget.classList.remove('loading');
                if (totalEl) totalEl.textContent = landingFormatCount(total);
                if (updatedEl) updatedEl.textContent = 'Last sync: ' + syncText;
                landingRenderSources(data.source_breakdown, total);
                if (dotEl) {
                    dotEl.classList.remove('bg-emerald-500', 'bg-amber-500');
                    dotEl.classList.add(total > 0 ? 'bg-emerald-500' : 'bg-amber-500');
                }
                if (stateEl) {
                    stateEl.textContent = total > 0
                        ? 'Database is online and query-ready on this instance.'
                        : 'Database is online and waiting for the first ingestion run.';
                }
            } catch (error) {
                if (widget) widget.classList.remove('loading');
                if (updatedEl) updatedEl.textContent = 'Unavailable';
                if (stateEl) stateEl.textContent = String(error);
            }
        }
        landingFetchDbStatus();
        window.addEventListener('scroll', () => {
            const header = document.querySelector('header');
            if (window.scrollY > 20) {
                header.classList.add('shadow-md');
            } else {
                header.classList.remove('shadow-md');
            }
        });
    </script>
</body>
</html>
"""
)


def render_landing_page(*, auth_enabled: bool, github_url: str = DEFAULT_GITHUB_URL) -> bytes:
    if auth_enabled:
        primary_cta_href = "/login"
        primary_cta_label = "Get Started"
        hero_cta_label = "Sign in to investigate"
        pipeline_cta_label = "Start investigating"
        database_cta_label = "Sign in to explore the database"
    else:
        primary_cta_href = APP_ROUTE
        primary_cta_label = "Open investigator"
        hero_cta_label = "Open investigator"
        pipeline_cta_label = "Open investigator"
        database_cta_label = "Open the investigator"

    html = LANDING_TEMPLATE.substitute(
        favicon_tag=favicon_link_tag(),
        logo_url=LETTERMARK_LOGO_URL_PATH,
        dashboard_image_url=LANDING_DASHBOARD_URL_PATH,
        current_year=str(datetime.now(timezone.utc).year),
        github_url=github_url,
        app_url=APP_ROUTE,
        primary_cta_href=primary_cta_href,
        primary_cta_label=primary_cta_label,
        hero_cta_label=hero_cta_label,
        pipeline_cta_label=pipeline_cta_label,
        database_cta_label=database_cta_label,
    )
    return html.encode("utf-8")
