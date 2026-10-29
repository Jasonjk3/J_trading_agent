<template>
  <div class="not-found">
    <div class="nf-content">
      <h1>404</h1>
      <p>页面不存在或已被移除</p>
      <el-button type="primary" round @click="$router.push('/')">返回首页</el-button>
    </div>
  </div>
</template>
<script setup lang="ts"></script>
<style scoped>
.not-found {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-base);
}
.nf-content {
  text-align: center;
}
.not-found h1 {
  margin: 0 0 8px;
  font-size: 80px;
  font-weight: 700;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  opacity: 0.5;
}
.not-found p {
  margin: 0 0 24px;
  font-size: var(--font-size-body);
  color: var(--color-text-muted);
}
</style>
