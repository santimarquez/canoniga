from __future__ import annotations

import json
from datetime import datetime, timezone
from string import Template

from als_intel.brand import (
    DEFAULT_GITHUB_URL,
    LANDING_DASHBOARD_URL_PATH,
    LETTERMARK_LOGO_URL_PATH,
    favicon_link_tag,
)
from als_intel.i18n import common_strings, landing_strings

APP_ROUTE = "/app"

LANDING_TEMPLATE = Template(
    """

<!DOCTYPE html>
<html class="scroll-smooth" lang="$html_lang">
<head>
<meta charset="utf-8"/>
<link rel="alternate" hreflang="en" href="/?lang=en" />
<link rel="alternate" hreflang="es" href="/?lang=es" />
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>$t_page_title</title>
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
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#database">$t_nav_database</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#features">$t_nav_features</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#how-it-works">$t_nav_how_it_works</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#governance">$t_nav_governance</a>
<a class="text-on-surface-variant hover:text-primary transition-colors font-body-sm text-body-sm" href="#open-source">$t_nav_community</a>
</div>
<div class="flex items-center gap-stack-md"><div class="hidden sm:flex items-center gap-1 text-on-surface-variant font-body-sm text-body-sm" aria-label="$t_lang_label"><a href="?lang=en" class="$lang_en_class">$t_lang_en</a><span>|</span><a href="?lang=es" class="$lang_es_class">$t_lang_es</a></div>
<a class="hidden sm:block text-on-surface-variant hover:text-primary font-body-sm text-body-sm transition-colors" href="/docs/MISSION.md">$t_nav_documentation</a>
<a class="bg-primary-container text-white px-5 py-2 rounded font-body-sm text-body-sm hover:opacity-90 transition-all active:scale-95 shadow-sm" href="$primary_cta_href">$primary_cta_label</a>
</div>
</nav>
</header>
<main class="pt-24 overflow-x-hidden">
<section class="max-w-container-max mx-auto px-margin-desktop py-stack-lg lg:py-24 grid grid-cols-1 lg:grid-cols-2 gap-gutter items-center">
<div class="space-y-stack-md">
<div class="inline-flex items-center px-3 py-1 bg-primary/5 text-primary-container border border-primary/10 rounded-full font-code-label text-code-label">
                    $t_hero_badge
                </div>
<h1 class="font-display-lg text-display-lg text-primary tracking-tight leading-tight">
                    $t_hero_title
                </h1>
<p class="text-on-surface-variant font-body-base text-body-base max-w-xl">
                    $t_hero_body
                </p>
<div class="flex flex-wrap gap-stack-md pt-stack-sm">
<a class="bg-primary-container text-white px-8 py-3 rounded-lg font-title-md text-title-md flex items-center gap-2 hover:bg-primary transition-all" href="$primary_cta_href">
                        $hero_cta_label
                        <span class="material-symbols-outlined">arrow_forward</span>
</a>
<a class="border border-outline-variant text-primary px-8 py-3 rounded-lg font-title-md text-title-md hover:bg-surface-container-low transition-all" href="$github_url" target="_blank" rel="noopener noreferrer">
                        $t_hero_github
                    </a>
</div>
<div class="flex items-center gap-2 text-outline font-body-sm text-body-sm pt-4">
<span class="material-symbols-outlined text-[18px]">verified_user</span>
                    $t_hero_trust
                </div>
</div>
<div class="relative group">
<div class="absolute -inset-4 bg-gradient-to-tr from-primary/5 to-secondary/10 blur-3xl opacity-50 rounded-full"></div>
<div class="relative rounded-xl border border-outline-variant overflow-hidden shadow-2xl">
<img alt="$t_hero_mockup_alt" class="w-full h-auto object-cover group-hover:scale-105 transition-transform duration-700" src="$dashboard_image_url"/>
</div>
</div>
</section>
<section class="bg-surface-container-low border-y border-outline-variant/30 py-12">
<div class="max-w-container-max mx-auto px-margin-desktop grid grid-cols-2 lg:grid-cols-4 gap-gutter text-center">
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">15</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">$t_stats_sources</div>
</div>
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">30k+</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">$t_stats_records</div>
</div>
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">55</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">$t_stats_fidelity</div>
</div>
<div class="space-y-1">
<div class="font-display-lg text-headline-lg text-primary">100%</div>
<div class="text-on-surface-variant font-body-sm text-body-sm uppercase tracking-wider">$t_stats_quality</div>
</div>
</div>
<p class="text-center text-on-surface-variant font-body-sm text-body-sm mt-6 px-margin-desktop">$t_stats_disclaimer</p>
</section>
<section class="max-w-container-max mx-auto px-margin-desktop py-24" id="database">
<div class="grid grid-cols-1 lg:grid-cols-2 gap-gutter items-center">
<div class="space-y-stack-md">
<div class="inline-flex items-center px-3 py-1 bg-primary/5 text-primary-container border border-primary/10 rounded-full font-code-label text-code-label">
                    $t_database_badge
                </div>
<h2 class="font-headline-lg text-headline-lg text-primary">$t_database_title</h2>
<p class="text-on-surface-variant font-body-base text-body-base max-w-xl">
                    $t_database_body
                </p>
<a class="inline-flex items-center gap-2 bg-primary-container text-white px-8 py-3 rounded-lg font-title-md text-title-md hover:bg-primary transition-all shadow-md active:scale-95" href="$primary_cta_href">
                    $database_cta_label
                    <span class="material-symbols-outlined">database</span>
                </a>
</div>
<div id="landingDbWidget" class="landing-db-widget rounded-xl p-stack-lg loading">
<div class="flex justify-between items-center mb-4">
<h3 class="font-title-md text-title-md text-primary">$t_database_status_title</h3>
<div class="flex items-center gap-2">
<span id="landingDbDot" class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
<span id="landingDbUpdated" class="text-on-surface-variant font-body-sm text-body-sm">$t_database_checking</span>
</div>
</div>
<div class="flex items-baseline gap-2 mb-4">
<span id="landingDbTotal" class="font-display-lg text-headline-lg text-primary">-</span>
<span class="text-on-surface-variant font-body-sm text-body-sm">$t_database_nodes_label</span>
</div>
<div id="landingDbSources" class="space-y-3 mb-4">
<div class="landing-db-skeleton h-2.5 w-full"></div>
<div class="landing-db-skeleton h-2.5 w-[86%]"></div>
<div class="landing-db-skeleton h-2.5 w-[73%]"></div>
</div>
<p id="landingDbState" class="text-on-surface-variant font-body-sm text-body-sm border-t border-outline-variant/30 pt-4">$t_database_loading_state</p>
</div>
</div>
</section>
<section class="max-w-container-max mx-auto px-margin-desktop py-24">
<h2 class="font-headline-lg text-headline-lg text-center mb-16 text-primary">$t_rigor_title</h2>
<div class="grid grid-cols-1 md:grid-cols-3 gap-gutter">
<div class="bento-card p-stack-lg bg-white border border-outline-variant rounded-xl border-l-4 border-l-secondary">
<div class="w-12 h-12 bg-primary/5 rounded-lg flex items-center justify-center text-primary mb-6">
<span class="material-symbols-outlined text-3xl">description</span>
</div>
<h3 class="font-title-md text-title-md mb-3 text-primary">$t_rigor_audit_title</h3>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">$t_rigor_audit_body</p>
</div>
<div class="bento-card p-stack-lg bg-white border border-outline-variant rounded-xl border-l-4 border-l-secondary">
<div class="w-12 h-12 bg-primary/5 rounded-lg flex items-center justify-center text-primary mb-6">
<span class="material-symbols-outlined text-3xl">compare</span>
</div>
<h3 class="font-title-md text-title-md mb-3 text-primary">$t_rigor_contradictions_title</h3>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">$t_rigor_contradictions_body</p>
</div>
<div class="bento-card p-stack-lg bg-white border border-outline-variant rounded-xl border-l-4 border-l-secondary">
<div class="w-12 h-12 bg-primary/5 rounded-lg flex items-center justify-center text-primary mb-6">
<span class="material-symbols-outlined text-3xl">storage</span>
</div>
<h3 class="font-title-md text-title-md mb-3 text-primary">$t_rigor_local_title</h3>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">$t_rigor_local_body</p>
</div>
</div>
</section>
<section class="bg-surface-container-lowest py-24" id="features">
<div class="max-w-container-max mx-auto px-margin-desktop">
<div class="max-w-2xl mb-16">
<h2 class="font-headline-lg text-headline-lg text-primary mb-4">$t_features_title</h2>
<p class="text-on-surface-variant">$t_features_subtitle</p>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">$t_features_sync_title</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">$t_features_sync_body</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">$t_features_extract_title</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">$t_features_extract_body</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">$t_features_chat_title</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">$t_features_chat_body</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">$t_features_hypothesis_title</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">$t_features_hypothesis_body</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">$t_features_atlas_title</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">$t_features_atlas_body</p>
</div>
<div class="p-8 border border-outline-variant hover:border-primary/30 transition-colors group">
<h4 class="font-title-md text-title-md text-primary mb-2">$t_features_automation_title</h4>
<p class="text-on-surface-variant font-body-sm text-body-sm mb-6">$t_features_automation_body</p>
</div>
</div>
</div>
</section>
<section class="py-24 max-w-container-max mx-auto px-margin-desktop" id="how-it-works">
<h2 class="font-headline-lg text-headline-lg text-center mb-16 text-primary">$t_pipeline_title</h2>
<div class="relative grid grid-cols-1 md:grid-cols-4 gap-gutter">
<div class="hidden md:block absolute top-12 left-0 w-full h-[2px] bg-outline-variant/30 z-0"></div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">1</div>
<h5 class="font-title-md text-title-md text-primary mb-2">$t_pipeline_ingest</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">$t_pipeline_ingest_body</p>
</div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">2</div>
<h5 class="font-title-md text-title-md text-primary mb-2">$t_pipeline_structure</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">$t_pipeline_structure_body</p>
</div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">3</div>
<h5 class="font-title-md text-title-md text-primary mb-2">$t_pipeline_investigate</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">$t_pipeline_investigate_body</p>
</div>
<div class="relative z-10 flex flex-col items-center text-center">
<div class="w-16 h-16 rounded-full bg-white border-2 border-primary flex items-center justify-center font-bold text-primary mb-6 shadow-md">4</div>
<h5 class="font-title-md text-title-md text-primary mb-2">$t_pipeline_validate</h5>
<p class="text-on-surface-variant font-body-sm text-body-sm">$t_pipeline_validate_body</p>
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
                        $t_governance_title
                    </h3>
<div class="grid grid-cols-1 md:grid-cols-2 gap-gutter">
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">
                            $t_governance_body1
                        </p>
<p class="text-on-surface-variant font-body-sm text-body-sm leading-relaxed">
                            $t_governance_body2 <a href="/docs/MISSION.md" class="text-primary hover:underline">/docs</a>.
                        </p>
</div>
</div>
</div>
</section>
<section class="py-24 bg-primary text-white overflow-hidden" id="open-source">
<div class="max-w-container-max mx-auto px-margin-desktop grid grid-cols-1 lg:grid-cols-2 gap-24 items-center">
<div>
<h2 class="font-display-lg text-headline-lg mb-6">$t_opensource_title</h2>
<p class="text-primary-fixed font-body-base text-body-base mb-8">
                        $t_opensource_body
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
<a class="inline-block mt-8 border border-white/40 text-white px-8 py-3 rounded-lg font-title-md hover:bg-white/10 transition-all" href="$github_url" target="_blank" rel="noopener noreferrer">$t_opensource_explore</a>
</div>
<div class="relative">
<div class="bg-surface-container-highest/10 backdrop-blur-md rounded-xl border border-white/20 p-6 font-code-label text-code-label text-primary-fixed shadow-2xl">
<div class="flex gap-2 mb-4">
<div class="w-3 h-3 rounded-full bg-error"></div>
<div class="w-3 h-3 rounded-full bg-secondary-container"></div>
<div class="w-3 h-3 rounded-full bg-on-primary-container"></div>
</div>
<div class="space-y-1 opacity-80">
<p><span class="text-on-tertiary-container">$t_opensource_comment_nightly</span></p>
<p>export ALS_AUTOMATION_WORKER_TOKEN="..."</p>
<p>make nightly-ops</p>
<p class="mt-4"><span class="text-secondary-container">$t_opensource_comment_fidelity</span></p>
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
                    © $current_year MTVL AI. $t_footer_body
                </p>
</div>
<div class="grid grid-cols-2 gap-gutter">
<div class="space-y-3">
<h6 class="font-title-md text-[14px] uppercase tracking-widest text-primary">$t_footer_resources</h6>
<ul class="space-y-2">
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/docs/MISSION.md">$t_nav_documentation</a></li>
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="$github_url" target="_blank" rel="noopener noreferrer">GitHub</a></li>
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/docs/ETHICS_AND_OVERSIGHT.md">$t_footer_research_ethics</a></li>
</ul>
</div>
<div class="space-y-3">
<h6 class="font-title-md text-[14px] uppercase tracking-widest text-primary">$t_footer_legal</h6>
<ul class="space-y-2">
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/privacy">$t_footer_privacy</a></li>
<li><a class="text-on-surface-variant hover:text-on-surface font-body-sm text-body-sm transition-all" href="/terms">$t_footer_terms</a></li>
</ul>
</div>
</div>
</div>
</footer>
<script>

        const LANDING_I18N = $landing_i18n_json;
        function landingFormatCount(value) {
            const count = Number(value || 0);
            if (!Number.isFinite(count) || count < 0) return '0';
            return count.toLocaleString();
        }
        function landingFormatRelative(isoText) {
            if (!isoText) return LANDING_I18N.time_na;
            const parsed = new Date(String(isoText));
            if (Number.isNaN(parsed.getTime())) return String(isoText);
            const minutes = Math.round((Date.now() - parsed.getTime()) / 60000);
            if (minutes < 1) return LANDING_I18N.time_just_now;
            if (minutes < 60) return LANDING_I18N.time_minutes_ago.replace('{n}', String(minutes));
            const hours = Math.round(minutes / 60);
            if (hours < 48) return LANDING_I18N.time_hours_ago.replace('{n}', String(hours));
            return LANDING_I18N.time_days_ago.replace('{n}', String(Math.round(hours / 24)));
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
                const source = String(row && row.source ? row.source : LANDING_I18N.unknown_source);
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
                if (updatedEl) updatedEl.textContent = LANDING_I18N.last_sync.replace('{time}', syncText);
                landingRenderSources(data.source_breakdown, total);
                if (dotEl) {
                    dotEl.classList.remove('bg-emerald-500', 'bg-amber-500');
                    dotEl.classList.add(total > 0 ? 'bg-emerald-500' : 'bg-amber-500');
                }
                if (stateEl) {
                    stateEl.textContent = total > 0
                        ? '$t_nav_database is online and query-ready on this instance.'
                        : '$t_nav_database is online and waiting for the first ingestion run.';
                }
            } catch (error) {
                if (widget) widget.classList.remove('loading');
                if (updatedEl) updatedEl.textContent = LANDING_I18N.unavailable;
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


def _landing_template_vars(
    *,
    locale: str,
    auth_enabled: bool,
    authenticated: bool,
    github_url: str,
) -> dict[str, str]:
    strings = landing_strings(locale)
    common = common_strings(locale)

    def _t(key: str) -> str:
        return strings.get(key, key)

    if not auth_enabled or authenticated:
        primary_cta_href = APP_ROUTE
        primary_cta_label = _t("cta.open_investigator")
        hero_cta_label = _t("cta.continue_investigating")
        pipeline_cta_label = _t("cta.open_investigator")
        database_cta_label = _t("cta.continue_database")
    else:
        primary_cta_href = "/login"
        primary_cta_label = _t("cta.get_started")
        hero_cta_label = _t("cta.sign_in_investigate")
        pipeline_cta_label = _t("cta.start_investigating")
        database_cta_label = _t("cta.sign_in_database")

    safe_locale = locale if locale in {"en", "es"} else "en"
    lang_en_class = "text-primary font-semibold" if safe_locale == "en" else "hover:text-primary"
    lang_es_class = "text-primary font-semibold" if safe_locale == "es" else "hover:text-primary"

    landing_i18n = {
        "time_na": common.get("time_na", "n/a"),
        "time_just_now": common.get("time_just_now", "just now"),
        "time_minutes_ago": common.get("time_minutes_ago", "{n}m ago"),
        "time_hours_ago": common.get("time_hours_ago", "{n}h ago"),
        "time_days_ago": common.get("time_days_ago", "{n}d ago"),
        "last_sync": common.get("time_last_sync", "Last sync: {time}"),
        "no_sources": strings.get("database.no_sources", ""),
        "unknown_source": strings.get("database.unknown_source", "unknown"),
        "ready": strings.get("database.ready", ""),
        "waiting": strings.get("database.waiting", ""),
        "unavailable": strings.get("database.unavailable", "Unavailable"),
    }

    vars_out: dict[str, str] = {
        "html_lang": safe_locale,
        "favicon_tag": favicon_link_tag(),
        "logo_url": LETTERMARK_LOGO_URL_PATH,
        "dashboard_image_url": LANDING_DASHBOARD_URL_PATH,
        "current_year": str(datetime.now(timezone.utc).year),
        "github_url": github_url,
        "app_url": APP_ROUTE,
        "primary_cta_href": primary_cta_href,
        "primary_cta_label": primary_cta_label,
        "hero_cta_label": hero_cta_label,
        "pipeline_cta_label": pipeline_cta_label,
        "database_cta_label": database_cta_label,
        "lang_en_class": lang_en_class,
        "lang_es_class": lang_es_class,
        "t_lang_label": common.get("lang.label", "Language"),
        "t_lang_en": common.get("lang.en", "EN"),
        "t_lang_es": common.get("lang.es", "ES"),
        "landing_i18n_json": json.dumps(landing_i18n, ensure_ascii=True),
    }
    for key, value in strings.items():
        vars_out["t_" + key.replace(".", "_")] = value
    return vars_out


def render_landing_page(
    *,
    auth_enabled: bool,
    authenticated: bool = False,
    github_url: str = DEFAULT_GITHUB_URL,
    locale: str = "en",
) -> bytes:
    html = LANDING_TEMPLATE.substitute(
        **_landing_template_vars(
            locale=locale,
            auth_enabled=auth_enabled,
            authenticated=authenticated,
            github_url=github_url,
        )
    )
    return html.encode("utf-8")
