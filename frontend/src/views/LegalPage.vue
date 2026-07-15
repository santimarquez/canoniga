<template>
  <article class="mx-auto max-w-3xl px-4 py-12">
    <RouterLink to="/" class="text-sm text-brand-primary hover:underline">{{ t('legal.back_home') }}</RouterLink>
    <h1 class="mt-4 text-3xl font-semibold text-slate-900">{{ title }}</h1>
    <div class="prose prose-sm mt-6 max-w-none text-slate-700" v-html="bodyHtml" />
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ doc: 'privacy' | 'terms' }>()
const { t } = useI18n()

const title = computed(() => (props.doc === 'privacy' ? t('legal.privacy_title') : t('legal.terms_title')))

const bodyHtml = computed(() => (props.doc === 'privacy' ? privacyHtml : termsHtml))

const privacyHtml = `
<p>MTVL AI is an open source research project. This page describes our local deployment defaults and expected data handling behavior.</p>
<h2>1. Data Collected</h2>
<p>The application can store scientific evidence rows, user account email for authentication, login sessions, and user activity logs used for auditability.</p>
<h2>2. Purpose</h2>
<p>Data is processed to support ALS and related motor neuron disease investigation, user authentication, and reproducible analysis workflows.</p>
<h2>3. Storage Model</h2>
<p>By default, data is stored locally in your configured SQLite database. Hosting operators are responsible for backups, retention, and access control.</p>
<h2>4. Third-Party Services</h2>
<p>When configured, external biomedical APIs and model endpoints may be queried to retrieve evidence and generate responses. Review your deployment settings before production use.</p>
<h2>5. Security</h2>
<p>Use HTTPS in production, secure cookie settings, and managed secrets for SMTP/API credentials. Restrict database access to trusted operators.</p>
<h2>6. Open Source Disclaimer</h2>
<p>MTVL AI is provided as open source software and can be self-hosted. Data governance obligations are determined by your organization and jurisdiction.</p>
`

const termsHtml = `
<p>These Terms of Service govern use of MTVL AI, an open source project for biomedical evidence analysis.</p>
<h2>1. Intended Use</h2>
<p>The software is intended for research support and investigation workflows. It does not provide medical advice.</p>
<h2>2. Operator Responsibilities</h2>
<p>Instance operators are responsible for deployment security, user access management, legal compliance, and data protection controls.</p>
<h2>3. Open Source License</h2>
<p>Use, modification, and redistribution are governed by the repository license. Verify the license terms in your local checkout before commercial usage.</p>
<h2>4. No Warranty</h2>
<p>The software is provided "as is" without warranties of any kind, to the maximum extent allowed by applicable law.</p>
<h2>5. Limitation of Liability</h2>
<p>Contributors and maintainers are not liable for direct or indirect damages arising from use, misuse, or inability to use the software.</p>
`
</script>
