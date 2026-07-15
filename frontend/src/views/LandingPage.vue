<template>
  <div class="min-h-screen bg-surface">
    <LandingHeader />
    <main>
      <LandingHero />
      <LandingStats />
      <LandingDbWidget />
      <LandingFeatures />
      <LandingPipeline />
      <LandingGovernance />
    </main>
    <LandingFooter />
  </div>
</template>

<script setup lang="ts">
import LandingDbWidget from '@/components/landing/LandingDbWidget.vue'
import LandingFeatures from '@/components/landing/LandingFeatures.vue'
import LandingFooter from '@/components/landing/LandingFooter.vue'
import LandingGovernance from '@/components/landing/LandingGovernance.vue'
import LandingHeader from '@/components/landing/LandingHeader.vue'
import LandingHero from '@/components/landing/LandingHero.vue'
import LandingPipeline from '@/components/landing/LandingPipeline.vue'
import LandingStats from '@/components/landing/LandingStats.vue'
</script>
