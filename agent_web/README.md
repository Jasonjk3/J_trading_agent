# 加密货币量化交易系统 - 前端

基于 Vue 3 + TypeScript + Vite 的静态前端，Mock 数据，后续可接入真实后端。

## 技术栈

- Vue 3 + TypeScript
- Vite 5
- Vue Router 4
- Pinia
- Element Plus
- Axios
- ECharts（后续图表使用）

## 第一阶段完成内容

- 项目初始化、路由、主布局（侧边栏 + 顶栏 + 内容区）
- 登录页、Token 模拟、登出清除状态
- Mock 机制：`VITE_USE_MOCK=true` 时拦截 `/api/auth/login`、`/api/auth/logout` 返回本地数据
- 占位页面：首页、用户管理、交易所配置、持仓、Agent、交易记录、收益分析、个人中心、404

## 运行

```bash
# 安装依赖
npm install

# 开发
npm run dev

# 构建
npm run build

# 预览构建结果
npm run preview
```

开发环境默认使用 Mock（见 `.env.development`）。接入后端时设置 `VITE_USE_MOCK=false` 并配置 `VITE_API_BASE_URL`。

## 路由

| 路径 | 说明 |
|------|------|
| `/login` | 登录（独立布局） |
| `/` | 重定向到 `/dashboard` |
| `/dashboard` | 首页 |
| `/users` | 用户管理 |
| `/exchange-accounts` | 交易所配置 |
| `/positions` | 持仓管理 |
| `/agents` | Agent 列表 |
| `/agents/:id` | Agent 配置 |
| `/orders` | 交易记录 |
| `/analytics` | 收益分析 |
| `/profile` | 个人中心 |

未匹配路径显示 404 页。
