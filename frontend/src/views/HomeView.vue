<template>
  <div class="home">
    <h1>AiSpeakMate</h1>
    <p>AI 语言学习助手</p>
    <router-link to="/scenes">开始练习</router-link>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: 16px;
}
h1 {
  font-size: 2rem;
  color: var(--accent-primary);
}
</style>